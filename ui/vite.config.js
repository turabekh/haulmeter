import { defineConfig } from "vite";

export default defineConfig({
  server: {
    host: true,
    port: 9008,
  },
  test: {
    environment: "node",
    include: ["test/**/*.test.js"],
  },
});
