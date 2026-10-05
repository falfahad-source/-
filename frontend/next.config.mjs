// NEXT_OUTPUT=export builds the site as static files (out/), for hosting without a Node
// server (render.yaml). Every page renders in the browser, so nothing is lost.
const config = process.env.NEXT_OUTPUT === "export" ? { output: "export" } : {};
export default config;
