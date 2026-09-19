FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
# Web köküne yalnız tarayıcıya sunulacak üç dosya girer. `COPY .` kullanılmaz:
# nginx.conf, testler ve dokümanlar web kökünde yayımlanmamalı.
COPY index.html app.js style.css /usr/share/nginx/html/
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
