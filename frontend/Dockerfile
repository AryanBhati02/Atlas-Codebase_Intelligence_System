#Frontend Dockerfile
# Node 20 Alpine — lightweight, fast
FROM node:20-alpine

WORKDIR /app

# Copy lock files first for layer-cache efficiency
COPY package.json package-lock.json ./

# Install exact versions from lock file
RUN npm ci

# Copy the rest of the source
COPY . .

EXPOSE 5173

# host (0.0.0.0) and port (5173) are declared in vite.config.ts,
# so no extra CLI flags are needed here.
CMD ["npm", "run", "dev"]
