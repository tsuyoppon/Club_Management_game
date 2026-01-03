"""expand staff roles to seven spec positions"""
from alembic import op
import sqlalchemy as sa
import uuid
from datetime import datetime

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '9c0d1e2f4b5c'
branch_labels = None
depends_on = None

NEW_ROLES = [
    'sales',
    'hometown',
    'operations',
    'promotion',
    'administration',
    'topteam',
    'academy',
]

OLD_ROLES = ['director', 'coach', 'scout']

ROLE_MAPPING_OLD_TO_NEW = {
    'director': 'sales',
    'coach': 'topteam',
    'scout': 'academy',
}

ROLE_MAPPING_NEW_TO_OLD = {
    'sales': 'director',
    'topteam': 'coach',
    'academy': 'scout',
    'hometown': 'director',
    'operations': 'director',
    'promotion': 'director',
    'administration': 'director',
}


def upgrade():
    conn = op.get_bind()

    # 1) Cast to text to allow type replacement
    op.execute("ALTER TABLE club_staffs ALTER COLUMN role TYPE TEXT USING role::text")

    # 2) Drop old enum and create new one
    op.execute("DROP TYPE staffrole")
    op.execute("CREATE TYPE staffrole AS ENUM ('" + "','".join(NEW_ROLES) + "')")

    # 3) Map existing values to new roles while column is text
    for old, new in ROLE_MAPPING_OLD_TO_NEW.items():
        op.execute(sa.text("UPDATE club_staffs SET role = :new WHERE role = :old"), {"new": new, "old": old})

    # 4) Apply new enum type
    op.execute("ALTER TABLE club_staffs ALTER COLUMN role TYPE staffrole USING role::staffrole")

    # 5) Insert missing roles per club with count=1 and default salary
    clubs = conn.execute(sa.text("SELECT id FROM clubs")).fetchall()
    for (club_id,) in clubs:
        existing_roles = {
            row[0]
            for row in conn.execute(sa.text("SELECT role FROM club_staffs WHERE club_id = :club_id"), {"club_id": club_id})
        }
        for role in NEW_ROLES:
            if role not in existing_roles:
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO club_staffs (id, club_id, role, count, next_count, hiring_target, salary_per_person, created_at, updated_at)
                        VALUES (:id, :club_id, :role, 1, NULL, NULL, 1000000, :now, :now)
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "club_id": club_id,
                        "role": role,
                        "now": datetime.utcnow(),
                    },
                )


def downgrade():
    conn = op.get_bind()

    # 1) Cast to text
    op.execute("ALTER TABLE club_staffs ALTER COLUMN role TYPE TEXT USING role::text")

    # 2) Map roles back to old set (best-effort)
    for new, old in ROLE_MAPPING_NEW_TO_OLD.items():
        op.execute(sa.text("UPDATE club_staffs SET role = :old WHERE role = :new"), {"old": old, "new": new})

    # 3) Deduplicate by keeping lowest UUID per club/role before reapplying enum
    conn.execute(
        sa.text(
            """
            DELETE FROM club_staffs cs
            USING club_staffs cs2
            WHERE cs.club_id = cs2.club_id
              AND cs.role = cs2.role
              AND cs.id > cs2.id
            """
        )
    )

    # 4) Drop new enum and recreate old one
    op.execute("DROP TYPE staffrole")
    op.execute("CREATE TYPE staffrole AS ENUM ('" + "','".join(OLD_ROLES) + "')")

    # 5) Apply old enum type
    op.execute("ALTER TABLE club_staffs ALTER COLUMN role TYPE staffrole USING role::staffrole")
*** End File