# Definition of Done

Une tâche est terminée lorsque tous les critères ci-dessous sont remplis.
Chacun est né d'un défaut réel constaté sur ce projet, indiqué entre parenthèses.

1. **La CI passe au vert**, vérifiée après le push et non supposée.
   (Quinze commits poussés sur une CI rouge, Sprints 9 et 10.)
2. **Des tests couvrent la logique touchée**, et le seuil de couverture est respecté.
   (Webhook Stripe sans aucun test, seul code modifiant le stock en production.)
3. **La documentation impactée est mise à jour dans le même commit.**
   (README Terraform cassé par la suppression d'un fichier d'exemple.)
4. **Les fichiers liés sont relus** : configuration, infrastructure, CI.
   (Service ecom contre dilane-shop, venv .venv contre Ecom : pipeline EC2 inopérant.)
5. **Aucun secret ni donnée personnelle dans le commit.**
   (db.sqlite3 versionnée, retirée de l'historique au Sprint 9.)
6. **Le message de commit est descriptif**, en anglais, à l'impératif.
   (Commits test3 à test6.)
7. **L'issue est rattachée au commit** : Closes pour une issue terminée, Refs sinon.
   (Critères cochés à tort, relevés en revue de fin de Sprint 9.)
8. **Toute vérification est lisible** : aucune sortie masquée, et un code de sortie
   n'est lu que sur la commande qu'il concerne.
   (Sortie redirigée vers /dev/null, $? lu sur un tail : Sprint 11.)
9. **Un garde-fou est vérifié dans les deux sens** : il laisse passer ce qui est
   correct et bloque ce qui ne l'est pas.
   (CI et seuil de couverture éprouvés par un échec volontaire : Sprint 11.)
