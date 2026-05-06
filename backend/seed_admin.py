#!/usr/bin/env python3
"""
StockAI Admin Seed Script
Creates the initial admin user in the database.

Usage:
    python seed_admin.py
    
Environment Variables:
    DATABASE_URL - PostgreSQL connection string
    ADMIN_SEED_PASSWORD - Temporary password for admin account (will be deleted after seed)
    ADMIN_EMAIL - Admin email (default: admin@stockai.io)
    ADMIN_USERNAME - Admin username (default: admin)
"""

import os
import sys
import json
import hashlib
from datetime import datetime

def seed_admin():
    """Seed the admin user into the database."""
    
    # Check if DATABASE_URL is set
    database_url = os.environ.get("DATABASE_URL", "")
    
    if not database_url:
        print("⚠️  No DATABASE_URL found. Skipping database seed.")
        print("   If using Railway, DATABASE_URL will be auto-injected.")
        print("   Running in standalone mode - no DB required.")
        return True
    
    admin_password = os.environ.get("ADMIN_SEED_PASSWORD", "")
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@stockai.io")
    admin_username = os.environ.get("ADMIN_USERNAME", "admin")
    
    if not admin_password:
        print("❌ ADMIN_SEED_PASSWORD environment variable is required!")
        print("   Set it before running seed, and DELETE it immediately after.")
        return False
    
    print(f"📧 Admin Email: {admin_email}")
    print(f"👤 Admin Username: {admin_username}")
    print(f"🔑 Admin Password: [SET - will be deleted after seed]")
    
    try:
        import psycopg2
        
        # Connect to database
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        
        # Create admin user
        password_hash = hashlib.sha256(admin_password.encode()).hexdigest()
        
        # Check if admin exists
        cur.execute("SELECT id FROM users WHERE username = %s OR email = %s", 
                    (admin_username, admin_email))
        existing = cur.fetchone()
        
        if existing:
            print(f"✅ Admin user already exists (id={existing[0]}), updating password...")
            cur.execute(
                "UPDATE users SET password_hash = %s, updated_at = %s WHERE id = %s",
                (password_hash, datetime.utcnow(), existing[0])
            )
        else:
            print("📝 Creating new admin user...")
            cur.execute(
                "INSERT INTO users (username, email, password_hash, role, created_at, updated_at) "
                "VALUES (%s, %s, %s, 'admin', %s, %s)",
                (admin_username, admin_email, password_hash, datetime.utcnow(), datetime.utcnow())
            )
        
        conn.commit()
        cur.close()
        conn.close()
        
        print("✅ Admin user seeded successfully!")
        print("")
        print("⚠️  IMPORTANT: DELETE the ADMIN_SEED_PASSWORD env var NOW!")
        print(f"   Railway: railway variables delete ADMIN_SEED_PASSWORD")
        print(f"   Or via Dashboard: Project > Variables > remove ADMIN_SEED_PASSWORD")
        
        return True
        
    except ImportError:
        print("❌ psycopg2 is not installed!")
        print("   Install it: pip install psycopg2-binary")
        return False
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("  StockAI Admin Seed Tool")
    print("=" * 60)
    print("")
    
    success = seed_admin()
    
    print("")
    if success:
        print("✅ Seed completed.")
    else:
        print("❌ Seed failed.")
        sys.exit(1)
