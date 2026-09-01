#!/bin/bash
# Nuotao AI OS Production Deployment Script
# Usage: ./deploy-production.sh [--initial]
#   --initial: Run initial setup (database migrations, agent initialization)

set -euo pipefail

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"
ENV_FILE="${PROJECT_DIR}/.env"
BACKUP_DIR="${PROJECT_DIR}/backups"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi

    if ! command -v docker compose &> /dev/null && ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi

    if [ ! -f "$ENV_FILE" ]; then
        log_error "Environment file .env not found. Please create it from .env.example."
        exit 1
    fi

    log_success "All prerequisites checked."
}

# Backup current state
backup_state() {
    log_info "Creating backup of current state..."
    mkdir -p "$BACKUP_DIR"
    local timestamp=$(date +%Y%m%d_%H%M%S)

    # Backup database
    if docker compose -f "$COMPOSE_FILE" ps postgres &> /dev/null; then
        log_info "Backing up PostgreSQL database..."
        docker compose -f "$COMPOSE_FILE" exec -T postgres pg_dump -U "${POSTGRES_USER:-nuotao}" "${POSTGRES_DB:-nuotao}" | gzip > "${BACKUP_DIR}/postgres_${timestamp}.sql.gz"
        log_success "Database backed up."
    fi

    # Backup .env
    cp "$ENV_FILE" "${BACKUP_DIR}/env_${timestamp}.bak"
    log_success "Environment file backed up."

    log_success "Backup completed: ${BACKUP_DIR}"
}

# Pull latest images
pull_images() {
    log_info "Pulling latest Docker images..."
    docker compose -f "$COMPOSE_FILE" pull
    log_success "Images pulled."
}

# Build images
build_images() {
    log_info "Building Docker images..."
    docker compose -f "$COMPOSE_FILE" build
    log_success "Images built."
}

# Stop existing containers
stop_containers() {
    log_info "Stopping existing containers..."
    docker compose -f "$COMPOSE_FILE" down
    log_success "Containers stopped."
}

# Start containers
start_containers() {
    log_info "Starting containers..."
    docker compose -f "$COMPOSE_FILE" up -d
    log_success "Containers started."
}

# Wait for services to be healthy
wait_for_health() {
    log_info "Waiting for services to become healthy..."
    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        local api_status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/healthz 2>/dev/null || echo "000")

        if [ "$api_status" = "200" ]; then
            log_success "API service is healthy (attempt ${attempt}/${max_attempts})."
            return 0
        fi

        log_warning "API service not healthy yet (attempt ${attempt}/${max_attempts}, status=${api_status})..."
        sleep 5
        attempt=$((attempt + 1))
    done

    log_error "API service did not become healthy within ${max_attempts} attempts."
    log_info "Showing container logs for debugging:"
    docker compose -f "$COMPOSE_FILE" logs --tail=50 api
    return 1
}

# Run database migrations
run_migrations() {
    log_info "Running database migrations..."
    docker compose -f "$COMPOSE_FILE" exec -T api alembic upgrade head
    log_success "Migrations completed."
}

# Initialize agents
initialize_agents() {
    log_info "Initializing AI agents..."
    docker compose -f "$COMPOSE_FILE" exec -T api python init_all_agents.py
    log_success "Agents initialized."
}

# Show status
show_status() {
    log_info "Current deployment status:"
    echo ""
    docker compose -f "$COMPOSE_FILE" ps
    echo ""

    # API health check
    local api_status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/healthz 2>/dev/null || echo "000")
    local ready_status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/readyz 2>/dev/null || echo "000")

    echo "API Health: ${api_status}"
    echo "API Ready: ${ready_status}"
    echo ""

    if [ "$api_status" = "200" ]; then
        log_success "Deployment is running successfully!"
        echo ""
        echo "API Documentation: http://localhost:8000/docs"
        echo "API Health: http://localhost:8000/api/v1/healthz"
        echo "API Ready: http://localhost:8000/api/v1/readyz"
    else
        log_warning "API service may not be fully ready. Check logs with: docker compose logs -f api"
    fi
}

# Main deployment flow
main() {
    local initial_setup=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --initial)
                initial_setup=true
                shift
                ;;
            *)
                log_error "Unknown argument: $1"
                exit 1
                ;;
        esac
    done

    echo ""
    echo "=========================================="
    echo "  Nuotao AI OS Production Deployment"
    echo "=========================================="
    echo ""

    # Step 1: Check prerequisites
    check_prerequisites

    # Step 2: Backup current state
    backup_state

    # Step 3: Pull and build images
    pull_images
    build_images

    # Step 4: Stop and start containers
    stop_containers
    start_containers

    # Step 5: Wait for health
    wait_for_health

    # Step 6: Initial setup if requested
    if [ "$initial_setup" = true ]; then
        log_info "Running initial setup..."
        run_migrations
        initialize_agents
        log_success "Initial setup completed."
    else
        # Always run migrations on deployment
        run_migrations
    fi

    # Step 7: Show status
    show_status

    echo ""
    log_success "Deployment completed successfully!"
    echo ""
    echo "Useful commands:"
    echo "  View logs:        docker compose -f ${COMPOSE_FILE} logs -f"
    echo "  View API logs:    docker compose -f ${COMPOSE_FILE} logs -f api"
    echo "  View Worker logs: docker compose -f ${COMPOSE_FILE} logs -f worker"
    echo "  Stop services:    docker compose -f ${COMPOSE_FILE} down"
    echo "  Start services:   docker compose -f ${COMPOSE_FILE} up -d"
    echo "  Scale workers:    docker compose -f ${COMPOSE_FILE} up -d --scale worker=4"
    echo ""
}

# Run main
main "$@"
