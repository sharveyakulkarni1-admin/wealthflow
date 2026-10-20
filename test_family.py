import unittest
from datetime import date

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from auth import create_access_token
from database import Base, get_db
from main import app
from models import User


class FamilyApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with self.session_factory() as session:
            session.add_all([
                User(
                    email="owner@example.com",
                    password_hash="unused",
                    full_name="Family Owner",
                    base_currency="USD",
                ),
                User(
                    email="member@example.com",
                    password_hash="unused",
                    full_name="Family Member",
                    base_currency="USD",
                ),
                User(
                    email="outsider@example.com",
                    password_hash="unused",
                    full_name="Outside User",
                    base_currency="USD",
                ),
            ])
            await session.commit()
            users = {
                user.email: user
                for user in (await session.scalars(select(User))).all()
            }

        async def override_get_db():
            async with self.session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        self.clients = {}
        for email, user in users.items():
            client = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://wealthflow.test",
            )
            client.cookies.set(
                "access_token",
                create_access_token(user.id, user.session_version),
            )
            self.clients[email] = client

    async def asyncTearDown(self):
        for client in self.clients.values():
            await client.aclose()
        app.dependency_overrides.clear()
        await self.engine.dispose()

    async def test_authentication_and_invitation_acceptance_and_decline(self):
        unauthenticated = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://wealthflow.test",
        )
        response = await unauthenticated.get("/api/families")
        await unauthenticated.aclose()
        self.assertEqual(response.status_code, 401)

        owner = self.clients["owner@example.com"]
        member = self.clients["member@example.com"]
        outsider = self.clients["outsider@example.com"]
        created = await owner.post("/api/families", json={"name": "Home"})
        self.assertEqual(created.status_code, 201, created.text)
        family_id = created.json()["id"]

        invite = await owner.post(
            f"/api/families/{family_id}/invitations",
            json={"email": "member@example.com"},
        )
        self.assertEqual(invite.status_code, 201, invite.text)
        invitations = await member.get("/api/family-invitations")
        self.assertEqual(invitations.status_code, 200)
        self.assertEqual(invitations.json()[0]["family_name"], "Home")
        accepted = await member.post(
            f"/api/family-invitations/{invite.json()['id']}/respond",
            json={"action": "accept"},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(len((await member.get("/api/families")).json()), 1)

        declined_invite = await owner.post(
            f"/api/families/{family_id}/invitations",
            json={"email": "outsider@example.com"},
        )
        self.assertEqual(declined_invite.status_code, 201, declined_invite.text)
        declined = await outsider.post(
            f"/api/family-invitations/{declined_invite.json()['id']}/respond",
            json={"action": "decline"},
        )
        self.assertEqual(declined.status_code, 200, declined.text)
        self.assertEqual(declined.json()["status"], "declined")
        self.assertEqual((await outsider.get("/api/families")).json(), [])
        owner_id = created.json()["owner_user_id"]
        self.assertEqual(
            (
                await member.delete(
                    f"/api/families/{family_id}/members/{owner_id}"
                )
            ).status_code,
            403,
        )
        member_id = next(
            item["user_id"]
            for item in (await owner.get(f"/api/families/{family_id}")).json()["members"]
            if item["user_id"] != owner_id
        )
        removed = await owner.delete(
            f"/api/families/{family_id}/members/{member_id}"
        )
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertEqual((await member.get("/api/families")).json(), [])

    async def test_personal_data_privacy_explicit_summary_consent_and_existing_records(self):
        owner = self.clients["owner@example.com"]
        member = self.clients["member@example.com"]
        family = (await owner.post("/api/families", json={"name": "Private by default"})).json()
        family_id = family["id"]
        invite = await owner.post(
            f"/api/families/{family_id}/invitations",
            json={"email": "member@example.com"},
        )
        await member.post(
            f"/api/family-invitations/{invite.json()['id']}/respond",
            json={"action": "accept"},
        )

        transaction = await owner.post(
            "/api/transactions",
            json={
                "transaction_date": date.today().isoformat(),
                "kind": "expense",
                "amount": 123.45,
                "currency": "USD",
                "category": "Private",
                "merchant": "Private merchant",
                "note": "Do not expose",
            },
        )
        self.assertEqual(transaction.status_code, 201, transaction.text)
        personal_budget = await owner.post(
            "/api/budgets",
            json={
                "category": "Personal",
                "amount": 300,
                "month": date.today().month,
                "year": date.today().year,
            },
        )
        self.assertEqual(personal_budget.status_code, 201, personal_budget.text)
        personal_goal = await owner.post(
            "/api/savings-goals",
            json={"name": "Private goal", "target_amount": 500, "currency": "USD"},
        )
        self.assertEqual(personal_goal.status_code, 201, personal_goal.text)

        self.assertEqual((await member.get("/api/transactions")).json(), [])
        self.assertEqual((await member.get("/api/budgets")).json(), [])
        self.assertEqual((await member.get("/api/savings-goals")).json(), [])
        dashboard = await member.get(f"/api/families/{family_id}/dashboard")
        self.assertEqual(dashboard.status_code, 200, dashboard.text)
        self.assertEqual(float(dashboard.json()["shared_summary"]["expenses"]), 0)
        self.assertNotIn("Private merchant", dashboard.text)
        self.assertNotIn("Do not expose", dashboard.text)

        enabled = await owner.patch(
            f"/api/families/{family_id}/settings",
            json={"share_financial_summary": True},
        )
        self.assertEqual(enabled.status_code, 200, enabled.text)
        dashboard = await member.get(f"/api/families/{family_id}/dashboard")
        self.assertEqual(float(dashboard.json()["shared_summary"]["expenses"]), 123.45)
        self.assertNotIn("Private merchant", dashboard.text)
        self.assertNotIn("Do not expose", dashboard.text)

        await owner.patch(
            f"/api/families/{family_id}/settings",
            json={"share_financial_summary": False},
        )
        dashboard = await member.get(f"/api/families/{family_id}/dashboard")
        self.assertEqual(float(dashboard.json()["shared_summary"]["expenses"]), 0)

    async def test_role_permissions_shared_budget_goal_and_family_isolation(self):
        owner = self.clients["owner@example.com"]
        member = self.clients["member@example.com"]
        outsider = self.clients["outsider@example.com"]
        family_id = (await owner.post("/api/families", json={"name": "Shared"})).json()["id"]
        invite = await owner.post(
            f"/api/families/{family_id}/invitations",
            json={"email": "member@example.com"},
        )
        await member.post(
            f"/api/family-invitations/{invite.json()['id']}/respond",
            json={"action": "accept"},
        )

        budget_payload = {
            "category": "Groceries",
            "amount": 400,
            "currency": "USD",
            "month": date.today().month,
            "year": date.today().year,
        }
        denied = await member.post(f"/api/families/{family_id}/budgets", json=budget_payload)
        self.assertEqual(denied.status_code, 403)
        member_invite = await member.post(
            f"/api/families/{family_id}/invitations",
            json={"email": "outsider@example.com"},
        )
        self.assertEqual(member_invite.status_code, 403)

        enabled = await owner.patch(
            f"/api/families/{family_id}/settings",
            json={"members_can_manage_resources": True},
        )
        self.assertEqual(enabled.status_code, 200)
        budget = await member.post(f"/api/families/{family_id}/budgets", json=budget_payload)
        self.assertEqual(budget.status_code, 201, budget.text)
        expense_date = date.today().replace(day=1).isoformat()
        expense = await member.post(
            f"/api/families/{family_id}/budgets/{budget.json()['id']}/expenses",
            json={"transaction_date": expense_date, "amount": 82.5, "description": "Shared groceries"},
        )
        self.assertEqual(expense.status_code, 201, expense.text)

        goal = await member.post(
            f"/api/families/{family_id}/goals",
            json={"name": "Family trip", "target_amount": 1000, "currency": "USD"},
        )
        self.assertEqual(goal.status_code, 201, goal.text)
        contribution = await owner.post(
            f"/api/families/{family_id}/goals/{goal.json()['id']}/contributions",
            json={"amount": 250},
        )
        self.assertEqual(contribution.status_code, 201, contribution.text)
        dashboard = await owner.get(f"/api/families/{family_id}/dashboard")
        self.assertEqual(float(dashboard.json()["budgets"][0]["spent_amount"]), 82.5)
        self.assertEqual(float(dashboard.json()["goals"][0]["saved_amount"]), 250)

        other_family = (await outsider.post("/api/families", json={"name": "Other"})).json()
        denied_dashboard = await outsider.get(f"/api/families/{family_id}/dashboard")
        self.assertEqual(denied_dashboard.status_code, 404)
        denied_expense = await outsider.post(
            f"/api/families/{other_family['id']}/budgets/{budget.json()['id']}/expenses",
            json={"transaction_date": expense_date, "amount": 10},
        )
        self.assertEqual(denied_expense.status_code, 404)

        member_personal = await member.post(
            "/api/transactions",
            json={
                "transaction_date": date.today().isoformat(),
                "kind": "expense",
                "amount": 17,
                "currency": "USD",
                "category": "Personal",
            },
        )
        self.assertEqual(member_personal.status_code, 201, member_personal.text)
        left = await member.post(f"/api/families/{family_id}/leave", json={})
        self.assertEqual(left.status_code, 200, left.text)
        personal_transactions = await member.get("/api/transactions")
        self.assertEqual(len(personal_transactions.json()), 1)
        self.assertEqual(
            (await member.get(f"/api/families/{family_id}/dashboard")).status_code,
            404,
        )

    async def test_notifications_are_private_and_owner_transfer_and_exit_work(self):
        owner = self.clients["owner@example.com"]
        member = self.clients["member@example.com"]
        family_id = (await owner.post("/api/families", json={"name": "Transfer"})).json()["id"]
        invite = await owner.post(
            f"/api/families/{family_id}/invitations",
            json={"email": "member@example.com"},
        )
        await member.post(
            f"/api/family-invitations/{invite.json()['id']}/respond",
            json={"action": "accept"},
        )
        detail = (await owner.get(f"/api/families/{family_id}")).json()
        member_id = next(item["user_id"] for item in detail["members"] if item["role"] == "member")

        owner_notifications = await owner.get(f"/api/families/{family_id}/notifications")
        self.assertEqual(owner_notifications.status_code, 200)
        notification_id = owner_notifications.json()[0]["id"]
        forbidden_read = await member.post(
            f"/api/families/{family_id}/notifications/{notification_id}/read"
        )
        self.assertEqual(forbidden_read.status_code, 404)
        marked_read = await owner.post(
            f"/api/families/{family_id}/notifications/{notification_id}/read"
        )
        self.assertEqual(marked_read.status_code, 200)

        no_successor = await owner.post(f"/api/families/{family_id}/leave", json={})
        self.assertEqual(no_successor.status_code, 409)
        transfer = await owner.post(
            f"/api/families/{family_id}/leave",
            json={"transfer_to_user_id": member_id},
        )
        self.assertEqual(transfer.status_code, 200, transfer.text)
        self.assertEqual((await member.get(f"/api/families/{family_id}")).json()["role"], "owner")
        self.assertEqual((await owner.get("/api/families")).json(), [])

        solo = (await owner.post("/api/families", json={"name": "Solo"})).json()
        closed = await owner.post(f"/api/families/{solo['id']}/leave", json={})
        self.assertEqual(closed.status_code, 200, closed.text)
        self.assertTrue(closed.json()["family_deleted"])
        self.assertEqual((await owner.get("/api/families")).json(), [])


if __name__ == "__main__":
    unittest.main()
