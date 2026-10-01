# syntax=docker/dockerfile:1
#
# Multi-stage production image for the DQA SPA.
# Build produces static assets; runtime is nginx only (no Node toolchain).
# Never inject VITE_DQA_DEV_ACTOR / VITE_DQA_DEV_ROLES into production builds.

FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY index.html ./
COPY tsconfig.json tsconfig.app.json tsconfig.node.json ./
COPY vite.config.ts eslint.config.js ./
COPY src ./src

# Production build only. Do not pass VITE_DQA_DEV_* build args/env here.
ENV NODE_ENV=production
RUN npm run build

FROM nginx:1.27-alpine AS runtime

# Ship hardened main config + SPA site + shared proxy params.
# Never inject VITE_DQA_DEV_* identity headers in this reverse proxy.
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.main.conf /etc/nginx/nginx.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY dqa_proxy_params.conf /etc/nginx/dqa_proxy_params.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=5s --retries=6 --start-period=10s \
  CMD wget -q --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
