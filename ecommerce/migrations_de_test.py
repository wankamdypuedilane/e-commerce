"""Outil partagé par les tests de migration (#49).

Rejoue les migrations jusqu'à une cible et renvoie l'état historique des
modèles à ce point, pour peupler une base « à l'ancienne » puis vérifier ce
qu'en fait la migration.
"""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


def migrer(cible=None):
    """Migre vers `cible` (liste de (app, migration|None)), ou jusqu'au bout.

    Renvoie le registre des modèles historiques correspondant à l'état atteint.
    """
    executeur = MigrationExecutor(connection)
    executeur.loader.build_graph()
    executeur.migrate(cible or executeur.loader.graph.leaf_nodes())
    # project_state n'accepte pas de cible « zéro » : l'état est
    # reconstruit à partir des migrations réellement appliquées.
    executeur.loader.build_graph()
    return executeur.loader.project_state(list(executeur.loader.applied_migrations)).apps
