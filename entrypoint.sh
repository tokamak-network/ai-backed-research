#!/bin/sh
# Railway persistent volume setup
# Mount a single volume at /app/persistent, then symlink data directories into it.
# This ensures SQLite DB, results, and published articles survive redeployments.

if [ -d "/app/persistent" ]; then
  mkdir -p /app/persistent/data
  mkdir -p /app/persistent/results
  mkdir -p /app/persistent/results/submissions
  mkdir -p /app/persistent/web-data
  mkdir -p /app/persistent/web-articles

  # Seed: merge bundled data into volume (copy new directories only)
  if [ -d "/app/seed-data" ]; then
    echo "[seed] Merging seed data into volume..."
    # Copy each subdirectory individually if it doesn't exist
    for dir in /app/seed-data/results/*; do
      if [ -d "$dir" ]; then
        dirname=$(basename "$dir")
        if [ ! -d "/app/persistent/results/$dirname" ]; then
          echo "[seed] Adding new report: $dirname"
          cp -r "$dir" "/app/persistent/results/$dirname"
        fi
      fi
    done
    # Copy web-articles and web-data (no-clobber for files)
    cp -rn /app/seed-data/web-articles/* /app/persistent/web-articles/ 2>/dev/null || true
    cp -rn /app/seed-data/web-data/* /app/persistent/web-data/ 2>/dev/null || true
    echo "[seed] Seed data merged successfully"
    # DB: only seed if missing (never overwrite running database)
    if [ ! -f /app/persistent/data/research.db ]; then
      echo "[seed] Seeding initial database..."
      cp /app/seed-data/data/research.db /app/persistent/data/ 2>/dev/null || true
    fi
  fi

  # Remove empty dirs created during build, replace with symlinks
  rm -rf /app/data /app/results /app/web/data /app/web/articles
  ln -sf /app/persistent/data /app/data
  ln -sf /app/persistent/results /app/results
  ln -sf /app/persistent/web-data /app/web/data
  ln -sf /app/persistent/web-articles /app/web/articles
fi

exec "$@"
