import argparse

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Membership, Organization, User


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an idempotent NeighborLink coordinator")
    parser.add_argument("--cognito-sub", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--organization-name", default="NeighborLink Douala")
    parser.add_argument("--organization-slug", default="neighborlink-douala")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with SessionLocal.begin() as session:
        organization = session.scalar(
            select(Organization).where(Organization.slug == args.organization_slug)
        )
        if organization is None:
            organization = Organization(
                name=args.organization_name,
                slug=args.organization_slug,
                timezone="Africa/Douala",
            )
            session.add(organization)
            session.flush()

        user = session.scalar(select(User).where(User.cognito_sub == args.cognito_sub))
        if user is None:
            user = User(
                cognito_sub=args.cognito_sub,
                email=args.email,
                display_name=args.display_name,
            )
            session.add(user)
            session.flush()
        else:
            user.email = args.email
            user.display_name = args.display_name

        membership = session.scalar(
            select(Membership).where(
                Membership.user_id == user.id,
                Membership.organization_id == organization.id,
            )
        )
        if membership is None:
            session.add(
                Membership(
                    user_id=user.id,
                    organization_id=organization.id,
                    role="coordinator",
                )
            )

        print(f"Coordinator ready for organization {organization.slug}")


if __name__ == "__main__":
    main()
