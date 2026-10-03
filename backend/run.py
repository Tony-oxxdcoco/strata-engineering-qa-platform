import os
import uvicorn
from strata.app import create_app

if __name__ == "__main__":
    uvicorn.run(create_app(), host=os.environ.get("STRATA_BIND", "127.0.0.1"), port=int(os.environ.get("STRATA_PORT", "4180")), workers=1)
