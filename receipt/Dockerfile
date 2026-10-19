# Which Nginx configuration the image serves with:
#   dev  - nginx/default.conf, plain HTTP for local use
#   prod - nginx/prod.conf.template, HTTPS behind Cloudflare
ARG NGINX_CONF=dev

FROM node:22-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --silent
COPY . .
# Left empty, the bundle falls back to Django's development address
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:stable-alpine AS nginx-dev
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
EXPOSE 80

FROM nginx:stable-alpine AS nginx-prod
# When the container starts, the Nginx image fills in the template from the
# environment and writes it to conf.d/default.conf. Only ${DOMAIN} is replaced.
ENV NGINX_ENVSUBST_FILTER=^DOMAIN$
COPY nginx/prod.conf.template /etc/nginx/templates/default.conf.template
COPY nginx/cloudflare-realip.conf /etc/nginx/conf.d/cloudflare-realip.conf
EXPOSE 80 443

FROM nginx-${NGINX_CONF}
COPY --from=builder /app/dist /usr/share/nginx/html
CMD ["nginx", "-g", "daemon off;"]
