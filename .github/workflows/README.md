GitHub Actions deployment setup

Required repository secrets:

- EC2_HOST: public IP or domain of the EC2 instance
- EC2_PORT: SSH port (usually 22)
- EC2_USER: SSH user (usually ubuntu)
- EC2_PROJECT_PATH: absolute project path on server (example: /home/ubuntu/ecommerce)
- EC2_SSH_KEY: private key content used for SSH deployment

Workflow behavior:

1. Runs CI on push to main: install deps, django check, django tests.
2. If CI passes, deploys to EC2:
   - git pull --ff-only origin main
   - pip install -r requirements.txt
   - python manage.py migrate --noinput
   - python manage.py collectstatic --noinput
   - restart gunicorn and nginx
   - python manage.py check --deploy

Notes:

- The server repository must have origin configured to your GitHub repo.
- The server must allow sudo for restarting services.
- Keep production secrets in server .env, never in GitHub repository.
