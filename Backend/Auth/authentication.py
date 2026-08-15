from fastapi import APIRouter, Depends, HTTPException, status

auth_route = APIRouter(prefix="auth")