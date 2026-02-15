import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { Server as SocketServer } from "net";
import { z } from "zod";

const PORT = 3000;
const HOST = "127.0.0.1";

// 1. Initialize Server
const server = new McpServer({
  name: "ShadowGraph",
  version: "1.0.0",
});

// 2. Define Tools
server.tool(
  "analyze_code_intent",
  {
    filePath: z.string(),
    selection: z.string()
  },
  async ({ filePath, selection }) => {
    // Real logic would query SQLite here
    return {
      content: [{
        type: "text",
        text: `Analysis for ${filePath}: No hidden intent found in graph.`
      }]
    };
  }
);

server.tool(
  "list_workspace_files",
  {
    pattern: z.string().optional()
  },
  async ({ pattern }) => {
    return {
      content: [{
        type: "text",
        text: `Workspace files matching "${pattern || "*"}": [example_file.ts, config.json]`
      }]
    };
  }
);

// 3. Listen on TCP Socket for MCP connections
const socketServer = new SocketServer((socket) => {
  console.error("[Shadow Graph] Client connected");

  // Create a raw transport for this socket
  socket.on("data", async (chunk) => {
    try {
      const message = JSON.parse(chunk.toString());
      const response = await server.handleMessage(message);
      socket.write(JSON.stringify(response) + "\n");
    } catch (error) {
      console.error("[Shadow Graph] Message error:", error);
    }
  });

  socket.on("error", (error) => {
    console.error("[Shadow Graph] Socket error:", error);
  });

  socket.on("end", () => {
    console.error("[Shadow Graph] Client disconnected");
  });
});

socketServer.listen(PORT, HOST, () => {
  console.error(`[Shadow Graph] MCP server listening on ${HOST}:${PORT}`);
  console.error("[Shadow Graph] Available tools: analyze_code_intent, list_workspace_files");
});

socketServer.on("error", (error) => {
  console.error("[Shadow Graph] Server error:", error);
});
