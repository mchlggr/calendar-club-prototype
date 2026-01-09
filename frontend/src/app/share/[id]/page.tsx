interface SharePageProps {
	params: Promise<{ id: string }>;
}

export default async function SharePage({ params }: SharePageProps) {
	const { id } = await params;

	return (
		<div className="flex min-h-screen flex-col items-center justify-center px-6 py-12">
			<div className="max-w-md text-center">
				<h1 className="mb-4 text-2xl font-semibold text-text-primary">
					Shared Calendar
				</h1>
				<p className="mb-6 text-text-secondary">
					Calendar ID: <code className="text-sm">{id}</code>
				</p>
				<p className="text-sm text-text-secondary">
					Shareable calendar links coming soon.
				</p>
			</div>
		</div>
	);
}
