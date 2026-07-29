from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import IntegrityError, transaction

from tunnels.models import TunnelIdentity
from tunnels.names import normalize_tunnel_name


class Command(BaseCommand):
    help = "Reserve a tunnel username and print its one-time agent token."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument(
            "--rotate",
            action="store_true",
            help="Replace the token when the username already exists.",
        )

    def handle(self, *args, **options):
        try:
            username = normalize_tunnel_name(options["username"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        identity = TunnelIdentity.objects.filter(username=username).first()
        if identity and not options["rotate"]:
            raise CommandError(
                f'Tunnel username "{username}" already exists. Use --rotate to replace its token.'
            )

        if identity is None:
            identity = TunnelIdentity(username=username)
        identity.enabled = True
        token = identity.issue_token()
        try:
            with transaction.atomic():
                identity.save()
        except IntegrityError as exc:
            raise CommandError(f'Tunnel username "{username}" was claimed concurrently.') from exc

        self.stdout.write(
            self.style.SUCCESS(f"Reserved https://{username}.{settings.TUNNEL_DOMAIN}")
        )
        self.stdout.write("Agent token (shown once):")
        self.stdout.write(token)
