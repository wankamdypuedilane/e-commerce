import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Category, Commande, OrderItem, Product


User = get_user_model()


def create_category(name="Vetements"):
	return Category.objects.create(name=name)


def create_product(category=None, title="T-shirt", price="29.99", stock=10):
	if category is None:
		category = create_category()
	return Product.objects.create(
		title=title,
		price=Decimal(price),
		description="Un super produit",
		category=category,
		stock=stock,
	)


def create_user(username="junior", email="junior@test.com", password="motdepasse123"):
	return User.objects.create_user(username=username, email=email, password=password)


class ProductModelTest(TestCase):
	def test_str_returns_title(self):
		product = create_product(title="Nike Air")
		self.assertEqual(str(product), "Nike Air")

	def test_display_image_url_returns_empty_when_no_image(self):
		product = create_product()
		self.assertEqual(product.display_image_url, "")


class CheckoutAccessTest(TestCase):
	def test_checkout_requires_login(self):
		response = self.client.get(reverse("checkout"))
		self.assertRedirects(
			response,
			"/connexion/?next=/checkout",
			fetch_redirect_response=False,
		)


class CheckoutBusinessRulesTest(TestCase):
	def setUp(self):
		self.user = create_user()
		self.product = create_product(price="100.00", stock=5)
		self.client.login(username="junior", password="motdepasse123")

	@override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLIC_KEY="", TAX_RATE_PERCENT="20")
	def test_server_side_price_is_used_and_tax_is_applied(self):
		items = json.dumps([
			{
				"id": self.product.id,
				"quantity": 1,
				"price": "0.01",  # Malicious client value, ignored server-side.
			}
		])

		response = self.client.post(
			reverse("checkout"),
			{
				"nom": "Junior",
				"email": "junior@test.com",
				"address": "1 rue de la Paix",
				"ville": "Brest",
				"pays": "France",
				"zipcode": "29200",
				"items": items,
			},
		)

		self.assertEqual(response.status_code, 302)

		order = Commande.objects.get(email="junior@test.com")
		self.assertEqual(order.subtotal_ht, Decimal("100.00"))
		self.assertEqual(order.tax_amount, Decimal("20.00"))
		self.assertEqual(order.total, Decimal("120.00"))

		order_item = OrderItem.objects.get(commande=order)
		self.assertEqual(order_item.price, Decimal("100.00"))
		self.assertEqual(order_item.quantity, 1)

	@override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLIC_KEY="")
	def test_stock_decrements_after_valid_checkout(self):
		initial_stock = self.product.stock
		items = json.dumps([{"id": self.product.id, "quantity": 2}])

		response = self.client.post(
			reverse("checkout"),
			{
				"nom": "Junior",
				"email": "stock@test.com",
				"address": "1 rue",
				"ville": "Brest",
				"pays": "France",
				"zipcode": "29200",
				"items": items,
			},
		)

		self.assertEqual(response.status_code, 302)
		self.product.refresh_from_db()
		self.assertEqual(self.product.stock, initial_stock - 2)

	@override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLIC_KEY="")
	def test_insufficient_stock_blocks_order(self):
		items = json.dumps([{"id": self.product.id, "quantity": 999}])

		response = self.client.post(
			reverse("checkout"),
			{
				"nom": "Junior",
				"email": "fail@test.com",
				"address": "1 rue",
				"ville": "Brest",
				"pays": "France",
				"zipcode": "29200",
				"items": items,
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Stock insuffisant")
		self.assertFalse(Commande.objects.filter(email="fail@test.com").exists())

		self.product.refresh_from_db()
		self.assertEqual(self.product.stock, 5)


class AuthFlowTest(TestCase):
	def test_signup_creates_user(self):
		response = self.client.post(
			reverse("inscription"),
			{
				"username": "nouveau",
				"email": "nouveau@test.com",
				"password1": "MotDePasse123!",
				"password2": "MotDePasse123!",
			},
			follow=True,
		)
		self.assertEqual(response.status_code, 200)
		self.assertTrue(User.objects.filter(username="nouveau").exists())

	def test_profile_redirects_when_anonymous(self):
		response = self.client.get(reverse("profil"))
		self.assertEqual(response.status_code, 302)
