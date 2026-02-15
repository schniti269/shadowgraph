import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { spawn, ChildProcess } from "child_process";
import * as path from "path";
import * as net from "net";

const PORT = 3000;
const HOST = "127.0.0.1";

async function test() {
    console.log("[TEST CLIENT] Starting Shadow Graph Server...");

    const serverProcess = spawn("node", [
        path.resolve("dist/server.js")
    ]);

    // Give server time to start
    await new Promise(resolve => setTimeout(resolve, 1000));

    console.log("[TEST CLIENT] Connecting to MCP server via socket...");

    const socket = net.createConnection(PORT, HOST);

    let buffer = "";

    socket.on("connect", async () => {
        console.log("[TEST CLIENT] ✓ Connected to server on " + HOST + ":" + PORT);

        // Send listTools request
        const listToolsReq = {
            jsonrpc: "2.0",
            id: 1,
            method: "tools/list",
            params: {}
        };

        console.log("[TEST CLIENT] Requesting available tools...");
        socket.write(JSON.stringify(listToolsReq) + "\n");
    });

    socket.on("data", (chunk) => {
        buffer += chunk.toString();
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
            if (!line.trim()) continue;

            try {
                const response = JSON.parse(line);
                console.log("[TEST CLIENT] Server response:", JSON.stringify(response, null, 2));

                if (response.result && response.result.tools) {
                    console.log(`[TEST CLIENT] ✓ Available tools: ${response.result.tools.map((t: any) => t.name).join(", ")}`);

                    // Now call a tool
                    const callToolReq = {
                        jsonrpc: "2.0",
                        id: 2,
                        method: "tools/call",
                        params: {
                            name: "analyze_code_intent",
                            arguments: {
                                filePath: "src/extension.ts",
                                selection: "const serverPath = context.asAbsolutePath(...)"
                            }
                        }
                    };

                    console.log("\n[TEST CLIENT] Calling analyze_code_intent...");
                    socket.write(JSON.stringify(callToolReq) + "\n");
                }

                if (response.result && response.result.content) {
                    console.log("[TEST CLIENT] ✓✓✓ Tool executed successfully ✓✓✓");
                    console.log("[TEST CLIENT] Result:", response.result.content);
                    socket.end();
                    serverProcess.kill();
                }
            } catch (e) {
                console.error("[TEST CLIENT] Parse error:", e);
            }
        }
    });

    socket.on("error", (error) => {
        console.error("[TEST CLIENT] ✗ Connection error:", error.message);
        serverProcess.kill();
    });

    socket.on("close", () => {
        console.log("[TEST CLIENT] Connection closed");
        serverProcess.kill();
    });
}

test().catch(console.error);

