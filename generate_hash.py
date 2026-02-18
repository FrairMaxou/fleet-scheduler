#!/usr/bin/env python3
"""Generate a bcrypt password hash for secrets.toml.

Usage:
    python generate_hash.py
"""
import getpass
import bcrypt

password = getpass.getpass("Password: ")
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
print(f"\nPaste this into secrets.toml:\n{hashed}")
