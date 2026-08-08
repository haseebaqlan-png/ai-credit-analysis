# V4 Railway hotfix

Cause:
The repository already contains a directory named `app`, while V4 also used a root module named `app.py`.
`uvicorn app:app` can therefore import the `app` package/directory instead of the intended root file,
producing:

`Attribute "app" not found in module "app"`.

Fix:
- Use `main.py` as the ASGI module.
- Run `uvicorn main:app`.
- Use `/workspace` as the container working directory to avoid confusing the code package with the container path.
