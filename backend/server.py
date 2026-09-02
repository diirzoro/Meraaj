import os
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import logging
from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

from db import db
from security import router as auth_router, seed_admin
from market import router as market_router
from wallet import router as wallet_router
from admin import router as admin_router
from admin_orders import router as admin_orders_router
from admin_analytics import router as admin_analytics_router
from admin_ops import router as admin_ops_router, ensure_indexes
from admin_packages import router as admin_packages_router
from admin_travelers import router as admin_travelers_router
from rbac import router as rbac_router
from orgs import router as orgs_router
from enterprise import router as enterprise_router
from cron import router as cron_router
from commissions import router as commissions_router, ensure_default_rule
from credit import router as credit_router
from finance import router as finance_router
from integration import router as integration_router, sim_router as rahal_sim_router
from individual import router as individual_router
from documents import router as documents_router

app = FastAPI(title="Meraaj Network API")

health = APIRouter(prefix="/api")


@health.get("/")
async def root():
    return {"message": "Meraaj Network API is running"}


app.include_router(health)
app.include_router(auth_router)
app.include_router(market_router)
app.include_router(wallet_router)
app.include_router(admin_router)
app.include_router(admin_orders_router)
app.include_router(admin_analytics_router)
app.include_router(commissions_router)
app.include_router(credit_router)
app.include_router(finance_router)
app.include_router(admin_ops_router)
app.include_router(admin_packages_router)
app.include_router(admin_travelers_router)
app.include_router(rbac_router)
app.include_router(orgs_router)
app.include_router(enterprise_router)
app.include_router(cron_router)
app.include_router(integration_router)
app.include_router(rahal_sim_router)
app.include_router(individual_router)
app.include_router(documents_router)

frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.packages.create_index("rahal_ref")
    await db.trip_passports.create_index([("package_id", 1), ("passport_norm", 1)], unique=True)
    await db.traveler_documents.create_index([("booking_id", 1), ("registrant_index", 1)])
    await db.cancellation_evidence.create_index("booking_id")
    await seed_admin()
    await ensure_indexes()
    await ensure_default_rule()
    logger.info("Meraaj Network API started; admin seeded.")


@app.on_event("shutdown")
async def shutdown():
    from db import client
    client.close()
