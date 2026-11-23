import os

import uvicorn

if __name__ == "__main__":
    # behind Caddy on the server: trust X-Forwarded-For only from localhost
    uvicorn.run("floorhand.api:app", host=os.environ.get("HOST", "127.0.0.1"),
                port=int(os.environ.get("PORT", "8790")), proxy_headers=True, forwarded_allow_ips="127.0.0.1")
