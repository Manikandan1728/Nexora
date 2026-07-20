# --- Stage 1: Builder ---
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first for layer caching
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

# Copy the rest of the frontend source
COPY frontend/ ./

# Build the React production bundle
RUN npm run build

# --- Stage 2: Runtime ---
FROM nginx:alpine

# Remove default nginx static assets
RUN rm -rf /usr/share/nginx/html/*

# Copy custom nginx configuration for SPA routing
COPY docker/frontend.nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose HTTP port
EXPOSE 80

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:80/ || exit 1

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
