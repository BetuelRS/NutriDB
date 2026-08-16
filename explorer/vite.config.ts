import { createReadStream, existsSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(process.env.NUTRIDB_ROOT ?? join(here, ".."));

function artifactMiddleware(): Plugin {
  return {
    name: "nutridb-artifacts",
    configureServer(server) {
      server.middlewares.use("/artifacts", (req, res, next) => {
        const name = req.url?.split("?")[0]?.replace(/^\/+/, "");
        if (!name || name.includes("/") || name.includes("..")) {
          res.statusCode = 400;
          res.end("bad artifact path");
          return;
        }
        const file = join(repoRoot, "build", "artifacts", name);
        if (!existsSync(file)) {
          res.statusCode = 404;
          res.end(`artifact not found: ${name} (run 'uv run nutridb build' first)`);
          return;
        }
        res.setHeader("Content-Length", statSync(file).size);
        createReadStream(file).pipe(res);
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), artifactMiddleware()],
  base: "./",
  build: {
    target: "es2022",
    sourcemap: false,
  },
});