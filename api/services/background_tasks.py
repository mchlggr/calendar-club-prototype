"""
Background tasks for async operations like Websets polling.

Handles long-running operations that push results via SSE
when complete.
"""

import asyncio
import logging
from dataclasses import dataclass

from api.models import SearchProfile
from api.services.exa_client import get_exa_client
from api.services.sse_connections import get_sse_manager

logger = logging.getLogger(__name__)

# Configuration
WEBSET_POLL_INTERVAL = 5.0  # seconds between polls
WEBSET_MAX_POLLS = 60  # max polls before giving up (5 min total)
WEBSET_TARGET_COUNT = 25  # target number of results


@dataclass
class WebsetTask:
    """Tracks a running Webset task."""

    session_id: str
    webset_id: str
    profile: SearchProfile
    task: asyncio.Task[None] | None = None


class BackgroundTaskManager:
    """Manages background tasks like Websets polling."""

    def __init__(self) -> None:
        self._webset_tasks: dict[str, WebsetTask] = {}
        self._lock = asyncio.Lock()

    async def start_webset_discovery(
        self,
        session_id: str,
        profile: SearchProfile,
    ) -> str | None:
        """Start a Websets deep discovery for a session.

        Args:
            session_id: Session to push results to
            profile: Search profile for the query

        Returns:
            Webset ID if started, None if failed
        """
        client = get_exa_client()

        # Build query from profile
        query_parts = ["events", "Columbus Ohio"]
        if profile.categories:
            query_parts.extend(profile.categories)
        if profile.keywords:
            query_parts.extend(profile.keywords)

        query = " ".join(query_parts)

        # Add criteria for events
        criteria = "Must be an upcoming event with date, time, and location"

        try:
            webset_id = await client.create_webset(
                query=query,
                count=WEBSET_TARGET_COUNT,
                criteria=criteria,
            )

            if not webset_id:
                logger.warning("Failed to create Webset for session %s", session_id)
                return None

            logger.info(
                "Created Webset %s for session %s with query: %s",
                webset_id,
                session_id,
                query,
            )

            # Start polling task
            task_info = WebsetTask(
                session_id=session_id,
                webset_id=webset_id,
                profile=profile,
            )

            async with self._lock:
                # Cancel existing task for this session if any
                if session_id in self._webset_tasks:
                    old_task = self._webset_tasks[session_id]
                    if old_task.task and not old_task.task.done():
                        old_task.task.cancel()

                task_info.task = asyncio.create_task(
                    self._poll_webset(task_info)
                )
                self._webset_tasks[session_id] = task_info

            return webset_id

        except Exception as e:
            logger.error("Error starting Webset discovery: %s", e, exc_info=True)
            return None

    async def _poll_webset(self, task_info: WebsetTask) -> None:
        """Poll a Webset until complete and push results."""
        client = get_exa_client()
        sse_manager = get_sse_manager()
        polls = 0

        try:
            while polls < WEBSET_MAX_POLLS:
                polls += 1
                await asyncio.sleep(WEBSET_POLL_INTERVAL)

                # Check if session is still connected
                if not sse_manager.has_connection(task_info.session_id):
                    logger.info(
                        "Session %s disconnected, stopping Webset poll",
                        task_info.session_id,
                    )
                    return

                webset = await client.get_webset(task_info.webset_id)
                if not webset:
                    logger.warning("Failed to get Webset %s", task_info.webset_id)
                    continue

                logger.debug(
                    "Webset %s status: %s, results: %s",
                    task_info.webset_id,
                    webset.status,
                    webset.num_results,
                )

                if webset.status == "completed":
                    if webset.results:
                        # Convert to event format
                        events_data = [
                            {
                                "id": f"webset-{result.id}",
                                "title": result.title,
                                "url": result.url,
                                "description": result.text[:200] if result.text else "",
                                "source": "webset",
                            }
                            for result in webset.results
                        ]

                        # Push more_events to session
                        await sse_manager.push_event(
                            task_info.session_id,
                            {
                                "type": "more_events",
                                "events": events_data,
                                "source": "webset",
                                "message": f"Found {len(events_data)} more events with deep search",
                            },
                        )

                        logger.info(
                            "Pushed %d Webset events to session %s",
                            len(events_data),
                            task_info.session_id,
                        )
                    else:
                        logger.info(
                            "Webset %s completed with no results",
                            task_info.webset_id,
                        )
                    return

                elif webset.status == "failed":
                    logger.warning(
                        "Webset %s failed for session %s",
                        task_info.webset_id,
                        task_info.session_id,
                    )
                    return

            # Max polls reached
            logger.warning(
                "Webset %s polling timeout for session %s",
                task_info.webset_id,
                task_info.session_id,
            )

        except asyncio.CancelledError:
            logger.info("Webset poll cancelled for session %s", task_info.session_id)
            raise
        except Exception as e:
            logger.error(
                "Error polling Webset %s: %s",
                task_info.webset_id,
                e,
                exc_info=True,
            )
        finally:
            # Cleanup
            async with self._lock:
                if task_info.session_id in self._webset_tasks:
                    del self._webset_tasks[task_info.session_id]

    async def cancel_session_tasks(self, session_id: str) -> None:
        """Cancel all background tasks for a session."""
        async with self._lock:
            if session_id in self._webset_tasks:
                task_info = self._webset_tasks[session_id]
                if task_info.task and not task_info.task.done():
                    task_info.task.cancel()
                del self._webset_tasks[session_id]
                logger.debug("Cancelled background tasks for session %s", session_id)


# Singleton instance
_manager: BackgroundTaskManager | None = None


def get_background_task_manager() -> BackgroundTaskManager:
    """Get the singleton background task manager."""
    global _manager
    if _manager is None:
        _manager = BackgroundTaskManager()
    return _manager
