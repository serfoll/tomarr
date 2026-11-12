import { createFileRoute } from "@tanstack/react-router";
import { BackendVersion } from "@/components/backend-version";

export const Route = createFileRoute("/")({ component: HomePage });

function HomePage() {
	return (
		<>
			<h1>Tomarr</h1>
			<BackendVersion />
		</>
	);
}
