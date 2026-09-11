import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';
import {
  AccessToken,
  AgentDispatchClient,
  RoomConfiguration,
  RoomAgentDispatch,
} from 'livekit-server-sdk';
import path from 'node:path';
import fs from 'node:fs';

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');

  return {
    plugins: [
      react(),
      {
        name: 'livekit-token-server',
        configureServer(server) {
          server.middlewares.use(async (req, res, next) => {
            if (req.url && req.url.startsWith('/api/recipients')) {
              try {
                const dbPath = path.resolve(process.cwd(), '..', 'my-voice-agent', 'agent_memory.db');
                if (!fs.existsSync(dbPath)) {
                  res.setHeader('Content-Type', 'application/json');
                  res.end(JSON.stringify({ recipients: [] }));
                  return;
                }
                const { DatabaseSync } = await import('node:sqlite');
                const db = new DatabaseSync(dbPath, { readOnly: true });
                let recipients: Array<{ name: string; email: string }> = [];
                try {
                  recipients = db.prepare(
                    'SELECT name, email FROM email_recipients ORDER BY last_used DESC LIMIT 5'
                  ).all() as Array<{ name: string; email: string }>;
                } catch {
                  // table may not exist yet
                }
                res.setHeader('Content-Type', 'application/json');
                res.end(JSON.stringify({ recipients }));
              } catch (err: any) {
                res.statusCode = 500;
                res.setHeader('Content-Type', 'application/json');
                res.end(JSON.stringify({ error: err?.message || 'Failed to fetch recipients' }));
              }
            } else if (req.url && req.url.startsWith('/api/token')) {
              try {
                const url = new URL(req.url, 'http://localhost');
                const room = url.searchParams.get('room') || 'my-agent-room';
                const identity =
                  url.searchParams.get('identity') ||
                  `user-${Math.random().toString(36).slice(2, 7)}`;
                const voice = url.searchParams.get('voice') || 'male';

                const apiKey = env.LIVEKIT_API_KEY || process.env.LIVEKIT_API_KEY;
                const apiSecret = env.LIVEKIT_API_SECRET || process.env.LIVEKIT_API_SECRET;
                const wsUrl = env.VITE_LIVEKIT_URL || env.LIVEKIT_URL || 'wss://vaani-pvpbffol.livekit.cloud';

                if (!apiKey || !apiSecret) {
                  res.statusCode = 500;
                  res.setHeader('Content-Type', 'application/json');
                  res.end(JSON.stringify({ error: 'LIVEKIT_API_KEY or LIVEKIT_API_SECRET missing' }));
                  return;
                }

                // Explicitly dispatch the LiveKit voice agent to this room with voice metadata
                try {
                  const httpUrl = wsUrl.replace(/^wss:\/\//, 'https://').replace(/^ws:\/\//, 'http://');
                  const dispatchClient = new AgentDispatchClient(httpUrl, apiKey, apiSecret);
                  await dispatchClient.createDispatch(room, 'my-agent', {
                    metadata: JSON.stringify({ voice }),
                  });
                } catch (dispatchErr: any) {
                  // If dispatch already exists or succeeds via roomConfig, log and continue
                  console.log('Dispatch notification:', dispatchErr?.message || dispatchErr);
                }

                const at = new AccessToken(apiKey, apiSecret, {
                  identity,
                  metadata: JSON.stringify({ voice }),
                  attributes: { voice },
                });
                at.addGrant({ roomJoin: true, room });
                at.roomConfig = new RoomConfiguration({
                  agents: [
                    new RoomAgentDispatch({
                      agentName: 'my-agent',
                      metadata: JSON.stringify({ voice }),
                    }),
                  ],
                });
                const token = await at.toJwt();

                res.setHeader('Content-Type', 'application/json');
                res.end(JSON.stringify({ token, url: wsUrl }));
              } catch (err: any) {
                res.statusCode = 500;
                res.setHeader('Content-Type', 'application/json');
                res.end(JSON.stringify({ error: err?.message || 'Token generation failed' }));
              }
            } else {
              next();
            }
          });
        },
      },
    ],
  };
});

