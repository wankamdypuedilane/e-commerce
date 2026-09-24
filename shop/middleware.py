"""Intergiciels propres au projet."""


class PermissionsPolicyMiddleware:
    """Ajoute l'en-tête Permissions-Policy, que Django n'envoie pas nativement.

    Interdit à la page l'accès aux fonctions du navigateur dont une boutique
    n'a pas besoin. payment=() désactive l'API de paiement du navigateur : le
    paiement passe par une redirection vers la page de Stripe. À revoir si le
    paiement est un jour intégré directement dans le site.
    """

    POLITIQUE = "camera=(), microphone=(), geolocation=(), usb=(), payment=()"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        reponse = self.get_response(request)
        reponse.setdefault("Permissions-Policy", self.POLITIQUE)
        return reponse
