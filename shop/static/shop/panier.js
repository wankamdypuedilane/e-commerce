/*
 * Panier : logique commune à toutes les pages (issue #50).
 *
 * Le panier vit dans le localStorage du navigateur, sous la clé posée par
 * base.html (window.cartStorageKey) : un panier par compte, un pour les
 * visiteurs. Chaque ligne est un tableau [quantité, nom, prix total,
 * stock maximum] indexé par l'identifiant du produit.
 *
 * Ce fichier regroupe ce que base.html, index.html et checkout.html
 * dupliquaient : lecture et écriture du panier, opérations sur les
 * quantités, popover de la barre de navigation. Il est chargé par
 * base.html avant les scripts propres à chaque page, qui l'utilisent
 * par window.Panier.
 */
window.Panier = (function () {
  var cle = window.cartStorageKey || "panier_guest";

  function charger() {
    var stocke = localStorage.getItem(cle);
    return stocke ? JSON.parse(stocke) : {};
  }

  // Panier de la page : un seul objet, modifié sur place et jamais
  // remplacé, pour que les scripts des pages en gardent la référence.
  var contenu = charger();

  function enregistrer() {
    localStorage.setItem(cle, JSON.stringify(contenu));
  }

  // Stock lu sur le bouton d'ajout du produit, s'il figure sur la page.
  function stockAffiche(id) {
    var bouton = document.getElementById(id);
    if (!bouton) return null;

    var stock = parseInt(bouton.getAttribute("data-stock") || "", 10);
    return Number.isFinite(stock) ? stock : null;
  }

  // --- Opérations sur les quantités ------------------------------------
  // Chacune renvoie true si le panier a changé, pour que l'appelant
  // rafraîchisse son affichage.

  function incrementer(id, verifierStock) {
    if (!contenu[id]) return false;

    var prixUnitaire = contenu[id][2] / contenu[id][0];
    if (verifierStock) {
      var maxStock = contenu[id][3];
      if (!Number.isFinite(maxStock)) {
        maxStock = stockAffiche(id);
        if (maxStock !== null) {
          contenu[id][3] = maxStock;
        }
      }

      if (Number.isFinite(maxStock) && contenu[id][0] >= maxStock) {
        alert("Stock maximum atteint pour ce produit.");
        return false;
      }
    }

    contenu[id][0] += 1;
    contenu[id][2] += prixUnitaire;
    enregistrer();
    return true;
  }

  function decrementer(id) {
    if (!contenu[id]) return false;

    var prixUnitaire = contenu[id][2] / contenu[id][0];
    contenu[id][0] -= 1;

    if (contenu[id][0] <= 0) {
      delete contenu[id];
    } else {
      contenu[id][2] -= prixUnitaire;
    }

    enregistrer();
    return true;
  }

  function supprimer(id) {
    if (!contenu[id]) return false;

    delete contenu[id];
    enregistrer();
    return true;
  }

  // --- Popover de la barre de navigation -------------------------------

  var boutonPanier = null;
  var modifiable = false;

  var ENTETE =
    "<h5 style='color:#2c3e50; border-bottom:2px solid #2c3e50; padding-bottom:5px;'>🛒 Votre panier</h5>";
  var VIDE = "<p style='margin:8px 0;'>Votre panier est vide.</p>";
  var VALIDER =
    "<a href='/checkout' class='btn btn-primary mt-3 w-100'>Valider votre commande</a>";

  function getPopover() {
    var instance = bootstrap.Popover.getInstance(boutonPanier);
    if (!instance) {
      // Déclenchement manuel : meilleur contrôle de l'ouverture et de la fermeture
      instance = new bootstrap.Popover(boutonPanier, {
        html: true,
        trigger: "manual",
        placement: "bottom",
        container: "body",
        sanitize: false,
        content: function () {
          return boutonPanier.getAttribute("data-bs-content") || "";
        },
      });
    }
    return instance;
  }

  // Lecture seule : relu dans le stockage à chaque affichage
  function lignesEnLecture(panier) {
    var html = "";
    var index = 1;
    for (var id in panier) {
      html +=
        "<div style='display:flex; justify-content:space-between; align-items:center; padding:6px 0; border-bottom:1px solid #eee;'><span>" +
        index +
        ". " +
        panier[id][1] +
        "</span><span class='badge bg-success rounded-pill'>x" +
        panier[id][0] +
        "</span></div>";
      index += 1;
    }
    return html;
  }

  // Modifiable : boutons +, - et Supprimer sur chaque ligne
  function lignesModifiables(panier) {
    var html = "";
    var index = 1;
    for (var id in panier) {
      var quantite = panier[id][0];
      var prixUnitaire = panier[id][2] / panier[id][0];
      html +=
        "<div style='padding:6px 0; border-bottom:1px solid #eee;'>" +
        "<div style='display:flex; justify-content:space-between; align-items:center; gap:8px;'><span>" +
        index +
        ". " +
        panier[id][1] +
        "</span><span class='badge bg-success rounded-pill'>x" +
        quantite +
        "</span></div>" +
        "<div style='display:flex; justify-content:flex-end; gap:6px; margin-top:8px;'>" +
        "<button type='button' class='btn btn-sm btn-outline-secondary cart-minus' data-id='" +
        id +
        "'>-</button>" +
        "<button type='button' class='btn btn-sm btn-outline-success cart-plus' data-id='" +
        id +
        "'>+</button>" +
        "<button type='button' class='btn btn-sm btn-outline-danger cart-remove' data-id='" +
        id +
        "'>Supprimer</button>" +
        "</div></div>";

      // Lignes d'un ancien format, sans stock maximum : complétées si le
      // produit est affiché sur la page.
      if (panier[id].length < 4) {
        var stockDeduit = stockAffiche(id);
        if (stockDeduit !== null) {
          panier[id][3] = stockDeduit;
          panier[id][2] = prixUnitaire * panier[id][0];
          enregistrer();
        }
      }
      index += 1;
    }
    return html;
  }

  function afficher() {
    if (!boutonPanier) return;

    var panier = modifiable ? contenu : charger();
    var html = ENTETE;
    var nombreArticles = 0;

    if (Object.keys(panier).length === 0) {
      html += VIDE;
    }
    for (var id in panier) {
      nombreArticles += panier[id][0];
    }
    html += modifiable ? lignesModifiables(panier) : lignesEnLecture(panier);
    if (Object.keys(panier).length > 0) {
      html += VALIDER;
    }

    boutonPanier.setAttribute("data-bs-content", html);
    var popover = getPopover();
    if (popover.tip && popover.tip.classList.contains("show")) {
      popover.setContent({ ".popover-body": html });
    }

    var compteur = document.getElementById("panier-count");
    if (compteur) {
      compteur.innerHTML = nombreArticles;
    }
  }

  // Installe le popover. Le premier appel décide du mode : index.html le
  // demande modifiable ; base.html l'installe ensuite en lecture seule
  // sur les autres pages, sans effet là où il est déjà installé.
  function initialiserPopover(options) {
    if (boutonPanier) return;

    boutonPanier = document.getElementById("panier");
    if (!boutonPanier) return;
    modifiable = Boolean(options && options.modifiable);

    $(document).on("click", "#panier", function (event) {
      event.preventDefault();
      event.stopPropagation();

      // Contenu mis à jour avant l'ouverture
      afficher();
      var popover = getPopover();
      if (popover.tip && popover.tip.classList.contains("show")) {
        popover.hide();
      } else {
        popover.show();
      }
    });

    if (modifiable) {
      $(document).on("click", ".cart-plus", function (event) {
        event.preventDefault();
        event.stopPropagation();
        if (incrementer(this.getAttribute("data-id"), true)) afficher();
      });

      $(document).on("click", ".cart-minus", function (event) {
        event.preventDefault();
        event.stopPropagation();
        if (decrementer(this.getAttribute("data-id"))) afficher();
      });

      $(document).on("click", ".cart-remove", function (event) {
        event.preventDefault();
        event.stopPropagation();
        if (supprimer(this.getAttribute("data-id"))) afficher();
      });
    }

    // Un clic hors du bouton et du popover ferme le popover
    $(document).on("click", function (event) {
      if ($(event.target).closest("#panier, .popover").length) {
        return;
      }

      var popover = bootstrap.Popover.getInstance(boutonPanier);
      if (popover) {
        popover.hide();
      }
    });

    afficher();
  }

  return {
    contenu: contenu,
    enregistrer: enregistrer,
    incrementer: incrementer,
    decrementer: decrementer,
    supprimer: supprimer,
    afficher: afficher,
    initialiserPopover: initialiserPopover,
  };
})();
