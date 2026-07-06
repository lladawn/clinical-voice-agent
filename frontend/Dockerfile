# Build from the frontend/ dir (compose sets context: ./frontend).
FROM node:20-slim

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

# NEXT_PUBLIC_* is inlined at build time. Default targets the host-mapped backend.
ARG NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
ENV NEXT_PUBLIC_BACKEND_URL=$NEXT_PUBLIC_BACKEND_URL
RUN npm run build

EXPOSE 3000
CMD ["npm", "start"]
