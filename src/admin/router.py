"""Main Admin Router for the Testing UI.

Defines the APIRouter with prefix="/admin" and the page view handler
that renders the Jinja2 template for the admin dashboard.

Requirements covered:
- 9.1: Serve under /admin URL prefix
- 9.2: Return rendered Jinja2 template for main layout
"""

import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.admin.api import killswitch, market_data, orders, risk, seed, users, workers
from src.admin import sse as sse_module

admin_router = APIRouter(prefix="/admin", tags=["admin"])

# Templates directory is at project root: templates/admin/
templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "../../templates/admin")
)

# Include API sub-routers
admin_router.include_router(market_data.router)
admin_router.include_router(users.router)
admin_router.include_router(workers.router)
admin_router.include_router(risk.router)
admin_router.include_router(killswitch.router)
admin_router.include_router(orders.router)
admin_router.include_router(seed.router)
admin_router.include_router(sse_module.router)


@admin_router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """Render the main admin UI with sidebar navigation.

    Returns the single-page admin dashboard template with all panel
    containers and SSE connection setup.
    """
    return templates.TemplateResponse(request=request, name="index.html")
