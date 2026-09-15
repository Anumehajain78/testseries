"""Set any account's password, from the server itself.

The last resort, and the only way back in for the exam cell.

Every other reset runs through the API: a candidate who has lost their slip is
reset by an administrator, and anyone who knows their current password can
change it themselves. Neither helps the administrator who has forgotten theirs,
because there is nobody above them to ask.

So the answer is physical. Whoever can run this already has a shell on the
machine that holds the database and the signing key — they could mint a token
for any account regardless. Requiring that access is not a weaker check than a
password, it is a stronger one, and it needs no email the college does not have.

    python -m scripts.reset_password admin@northbridge.edu
    python -m scripts.reset_password admin@northbridge.edu --password 'something known'

Every sign-in that account had is ended, on every device.
"""

import argparse
import secrets
import string
import sys

from sqlalchemy import select, update

from app.core.security import hash_secret
from app.db.models import RefreshToken, User
from app.db.session import SessionLocal
from app.utils.clock import utcnow

#: Readable but not guessable, and without the characters people misread when a
#: password is written on a slip and carried across a building.
ALPHABET = "".join(c for c in string.ascii_letters + string.digits if c not in "O0lI1")


def generate() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(12))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("email", help="the account to reset")
    parser.add_argument(
        "--password",
        help="set this instead of generating one. Shown in your shell history, so prefer the generated one.",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.email.lower()))
        if user is None:
            print(f"No account with the address {args.email}.", file=sys.stderr)
            return 1

        password = args.password or generate()
        user.password_hash = hash_secret(password)

        # Ended everywhere. A password is reset because the old one is no
        # longer trusted, and a session it opened must not outlive it.
        ended = db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.consumed_at.is_(None))
            .values(consumed_at=utcnow())
        ).rowcount
        db.commit()

        print(f"\n  {user.full_name} <{user.email}>  ({user.role.value})")
        print(f"  new password: {password}")
        print(f"  {ended} sign-in(s) ended\n")
        print("  This is the only time it is readable. Give it to them, then close this window.")
        if args.password:
            print("  It is also in your shell history — clear that if it matters.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
