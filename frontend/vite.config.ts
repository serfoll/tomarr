import { fileURLToPath } from "node:url";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import { apiProxy } from "./vite-proxy.ts";

export default defineConfig({
	plugins: [tanstackRouter({ target: "react" }), react()],
	resolve: {
		alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
	},
	// The dev key stays in this Node process: Vite only exposes VITE_ variables to the bundle.
	server: { proxy: apiProxy(process.env.TOMARR_DEV_API_KEY) },
	test: {
		environment: "jsdom",
		setupFiles: ["./tests/setup.ts"],
		unstubGlobals: true,
	},
});
