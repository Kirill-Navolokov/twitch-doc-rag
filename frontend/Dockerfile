FROM node:22-slim

ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json /app/
RUN npm ci

COPY frontend /app

# The dev server, never `next build` + `next start`: Next.js inlines every NEXT_PUBLIC_* value into
# the bundle at build time, and NEXT_PUBLIC_API_URL only exists as a run-time variable supplied by
# docker-compose. `next dev` reads it from process.env as it serves, so the compose value is the one
# that reaches the browser.
CMD ["./node_modules/.bin/next", "dev", "--hostname", "0.0.0.0"]
