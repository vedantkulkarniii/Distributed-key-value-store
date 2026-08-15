# 🐳 Docker Deployment Guide

**Date**: August 15, 2026  
**Status**: ✅ Complete Docker Setup Guide

---

## 📋 Overview

This guide explains how to deploy the Distributed Key-Value Store using Docker. Docker allows you to package the entire application and run it anywhere.

---

## 🚀 Quick Start with Docker

### Prerequisites
- Docker installed ([Download Docker](https://www.docker.com/products/docker-desktop))
- Docker Compose (included with Docker Desktop)

### Option 1: Run a Single Node

```bash
# Build the Docker image
docker build -t dkvs:latest .

# Run a single node
docker run -p 8000:8000 \
  --name dkvs-node1 \
  -e NODE_ID=1 \
  dkvs:latest
```

Access at: `http://localhost:8000`

### Option 2: Run Multi-Node Cluster with Docker Compose

```bash
# Clone repository
git clone https://github.com/vedantkulkarniii/Distributed-key-value-store.git
cd Distributed-key-value-store

# Start cluster
docker-compose up -d

# View logs
docker-compose logs -f

# Stop cluster
docker-compose down
```

This starts:
- 3 backend nodes (ports 8001-8003)
- 1 frontend proxy (port 8000)
- Automatic health checks

---

## 📦 Dockerfile

Create `Dockerfile` in project root:

```dockerfile
# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY frontend/ ./frontend/

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 🐳 Docker Compose Setup

Create `docker-compose.yml` for multi-node cluster:

```yaml
version: '3.8'

services:
  # Node 1 - Leader
  node1:
    build: .
    container_name: dkvs-node1
    environment:
      NODE_ID: 1
      PEER_ADDRESSES: "node2:9000,node3:9000"
      API_PORT: 8000
      RPC_PORT: 9000
    ports:
      - "8001:8000"
      - "9001:9000"
    volumes:
      - dkvs_data1:/app/data
    networks:
      - dkvs_network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 10s
    restart: unless-stopped

  # Node 2 - Follower
  node2:
    build: .
    container_name: dkvs-node2
    environment:
      NODE_ID: 2
      PEER_ADDRESSES: "node1:9000,node3:9000"
      API_PORT: 8000
      RPC_PORT: 9000
    ports:
      - "8002:8000"
      - "9002:9000"
    volumes:
      - dkvs_data2:/app/data
    networks:
      - dkvs_network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 10s
    restart: unless-stopped
    depends_on:
      - node1

  # Node 3 - Follower
  node3:
    build: .
    container_name: dkvs-node3
    environment:
      NODE_ID: 3
      PEER_ADDRESSES: "node1:9000,node2:9000"
      API_PORT: 8000
      RPC_PORT: 9000
    ports:
      - "8003:8000"
      - "9003:9000"
    volumes:
      - dkvs_data3:/app/data
    networks:
      - dkvs_network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 10s
    restart: unless-stopped
    depends_on:
      - node1

  # Frontend Proxy (optional)
  frontend:
    image: nginx:alpine
    container_name: dkvs-frontend
    ports:
      - "8000:80"
    volumes:
      - ./frontend:/usr/share/nginx/html:ro
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    networks:
      - dkvs_network
    depends_on:
      - node1

networks:
  dkvs_network:
    driver: bridge

volumes:
  dkvs_data1:
  dkvs_data2:
  dkvs_data3:
```

---

## 🌐 Nginx Configuration

Create `nginx.conf` for load balancing:

```nginx
upstream dkvs_cluster {
    server node1:8000;
    server node2:8000;
    server node3:8000;
}

server {
    listen 80;
    server_name localhost;

    # API endpoints
    location /kv {
        proxy_pass http://dkvs_cluster;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        proxy_pass http://dkvs_cluster;
    }

    location /info {
        proxy_pass http://dkvs_cluster;
    }

    location /docs {
        proxy_pass http://dkvs_cluster;
    }

    # Frontend
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }
}
```

---

## 🚀 Deployment Commands

### Basic Commands

```bash
# Build image
docker build -t dkvs:latest .

# Run single container
docker run -p 8000:8000 dkvs:latest

# Run with data persistence
docker run -p 8000:8000 \
  -v dkvs_data:/app/data \
  dkvs:latest

# Run with environment variables
docker run -p 8000:8000 \
  -e LOG_LEVEL=INFO \
  -e API_PORT=8000 \
  dkvs:latest

# View logs
docker logs container_id

# Stop container
docker stop container_id

# Remove container
docker rm container_id
```

### Docker Compose Commands

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f node1

# Stop all services
docker-compose down

# Remove all volumes (WARNING: deletes data)
docker-compose down -v

# Restart services
docker-compose restart

# View running containers
docker-compose ps

# Execute command in container
docker-compose exec node1 bash
```

---

## 📊 Monitoring Docker

### View Container Status

```bash
# List running containers
docker ps

# List all containers
docker ps -a

# View container stats
docker stats

# View container logs
docker logs --tail=100 -f container_name
```

### Health Checks

```bash
# Check container health
docker inspect container_name

# Manual health check
curl http://localhost:8000/health

# Check cluster status
for port in 8001 8002 8003; do
  echo "Node on port $port:"
  curl http://localhost:$port/info
done
```

---

## 🔧 Configuration

### Environment Variables

```bash
# API Configuration
API_PORT=8000           # API port
API_HOST=0.0.0.0        # API host

# Node Configuration
NODE_ID=1               # Unique node ID
PEER_ADDRESSES=localhost:9000,localhost:9001

# RPC Configuration
RPC_PORT=9000           # RPC port
RPC_HOST=0.0.0.0        # RPC host

# Logging
LOG_LEVEL=INFO          # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT=json         # json or text

# Performance
MAX_WORKERS=4           # Worker threads
BUFFER_SIZE=10000       # Buffer size
```

### Volume Mounting

```bash
# Persist data directory
docker run -v dkvs_data:/app/data dkvs:latest

# Mount config file
docker run -v ./config.json:/app/config.json dkvs:latest

# Mount logs directory
docker run -v dkvs_logs:/app/logs dkvs:latest
```

---

## 🌍 Kubernetes Deployment

### Deployment Manifest

Create `k8s-deployment.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: dkvs

---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: dkvs-cluster
  namespace: dkvs
spec:
  serviceName: dkvs
  replicas: 3
  selector:
    matchLabels:
      app: dkvs
  template:
    metadata:
      labels:
        app: dkvs
    spec:
      containers:
      - name: dkvs
        image: dkvs:latest
        ports:
        - containerPort: 8000
          name: api
        - containerPort: 9000
          name: rpc
        env:
        - name: NODE_ID
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: PEER_ADDRESSES
          value: "dkvs-0:9000,dkvs-1:9000,dkvs-2:9000"
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
        volumeMounts:
        - name: data
          mountPath: /app/data
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: [ "ReadWriteOnce" ]
      resources:
        requests:
          storage: 10Gi

---
apiVersion: v1
kind: Service
metadata:
  name: dkvs
  namespace: dkvs
spec:
  clusterIP: None
  selector:
    app: dkvs
  ports:
  - port: 8000
    targetPort: 8000
    name: api
  - port: 9000
    targetPort: 9000
    name: rpc

---
apiVersion: v1
kind: Service
metadata:
  name: dkvs-api
  namespace: dkvs
spec:
  type: LoadBalancer
  selector:
    app: dkvs
  ports:
  - port: 80
    targetPort: 8000
    protocol: TCP
```

### Deploy to Kubernetes

```bash
# Create namespace and deploy
kubectl apply -f k8s-deployment.yaml

# Check status
kubectl get pods -n dkvs
kubectl get svc -n dkvs

# View logs
kubectl logs -n dkvs dkvs-0

# Forward port to localhost
kubectl port-forward -n dkvs svc/dkvs-api 8000:80

# Scale cluster
kubectl scale statefulset -n dkvs dkvs-cluster --replicas=5

# Delete deployment
kubectl delete -f k8s-deployment.yaml
```

---

## ☁️ Cloud Platform Deployment

### AWS (ECR + ECS)

```bash
# Create ECR repository
aws ecr create-repository --repository-name dkvs

# Build and push
docker build -t dkvs:latest .
docker tag dkvs:latest AWS_ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/dkvs:latest
docker push AWS_ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/dkvs:latest

# Deploy with ECS Fargate
aws ecs create-service \
  --cluster default \
  --service-name dkvs-service \
  --task-definition dkvs-task \
  --desired-count 3 \
  --launch-type FARGATE
```

### Google Cloud (GCR + GKE)

```bash
# Push to Google Container Registry
docker tag dkvs:latest gcr.io/PROJECT_ID/dkvs:latest
docker push gcr.io/PROJECT_ID/dkvs:latest

# Deploy to GKE
kubectl create deployment dkvs \
  --image=gcr.io/PROJECT_ID/dkvs:latest \
  --replicas=3

kubectl expose deployment dkvs \
  --type=LoadBalancer \
  --port=80 \
  --target-port=8000
```

### Azure (ACR + AKS)

```bash
# Push to Azure Container Registry
docker tag dkvs:latest myregistry.azurecr.io/dkvs:latest
docker push myregistry.azurecr.io/dkvs:latest

# Deploy to AKS
kubectl create deployment dkvs \
  --image=myregistry.azurecr.io/dkvs:latest \
  --replicas=3

kubectl expose deployment dkvs \
  --type=LoadBalancer \
  --port=80 \
  --target-port=8000
```

---

## 🔒 Security Best Practices

### 1. Use Health Checks

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
```

### 2. Resource Limits

```yaml
resources:
  requests:
    memory: "256Mi"
    cpu: "250m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```

### 3. Non-Root User

```dockerfile
RUN useradd -m appuser
USER appuser
```

### 4. Read-Only Filesystem

```yaml
securityContext:
  readOnlyRootFilesystem: true
```

### 5. Network Policies

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: dkvs-network-policy
spec:
  podSelector:
    matchLabels:
      app: dkvs
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: frontend
```

---

## 🧪 Testing Docker Deployment

### Basic Tests

```bash
# Test API
curl http://localhost:8000/health
curl http://localhost:8000/kv
curl -X POST http://localhost:8000/kv/test \
  -H "Content-Type: application/json" \
  -d '{"value": "test"}'

# Test cluster (if using compose)
for port in 8001 8002 8003; do
  echo "Testing port $port"
  curl http://localhost:$port/health
done
```

### Load Testing

```bash
# Using Apache Bench
ab -n 1000 -c 10 http://localhost:8000/kv

# Using hey (https://github.com/rakyll/hey)
hey -n 1000 -c 10 http://localhost:8000/kv

# Using wrk (https://github.com/wg/wrk)
wrk -t4 -c100 -d30s http://localhost:8000/kv
```

---

## 📋 Troubleshooting

### Container Won't Start

```bash
# Check logs
docker logs container_name

# Check image exists
docker images

# Check ports
docker port container_name

# Rebuild image
docker build --no-cache -t dkvs:latest .
```

### API Not Responding

```bash
# Check container health
docker inspect --format='{{.State.Health.Status}}' container_name

# Check logs
docker logs -f container_name

# Restart container
docker restart container_name

# Check port mapping
docker port container_name
```

### Data Loss

```bash
# Check volume
docker volume ls
docker volume inspect volume_name

# Backup data
docker run -v dkvs_data:/data \
  -v $(pwd):/backup \
  alpine cp -r /data /backup/

# Restore data
docker run -v dkvs_data:/data \
  -v $(pwd):/backup \
  alpine cp -r /backup/data /
```

---

## 📚 Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Guide](https://docs.docker.com/compose/)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [AWS ECS Guide](https://docs.aws.amazon.com/ecs/)

---

**Version**: 1.0  
**Last Updated**: August 15, 2026  
**Status**: ✅ Complete

