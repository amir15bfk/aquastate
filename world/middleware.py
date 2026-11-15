"""Serve the friendly 404 page (with the Catch-the-Rain mini-game) for HTML requests.

With DEBUG=False Django's default handler already renders templates/404.html. With DEBUG=True it
shows the technical 404 instead, so this middleware swaps it for the friendly page on HTML
navigations. API, static and admin paths keep their normal responses.
"""
from __future__ import annotations

from django.template.loader import render_to_string
from django.http import HttpResponseNotFound

SKIP_PREFIXES = ("/api/", "/static/", "/admin/", "/media/")


class FriendlyNotFoundMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code != 404 or request.path.startswith(SKIP_PREFIXES):
            return response
        if "text/html" not in (request.headers.get("Accept") or "text/html"):
            return response
        if request.GET.get("debug404") == "1":  # developer escape hatch: keep Django's debug page
            return response
        html = render_to_string("404.html", {"request_path": request.path}, request=request)
        return HttpResponseNotFound(html)
