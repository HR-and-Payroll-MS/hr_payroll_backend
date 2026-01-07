from django.db import migrations


def drop_attendance_tables(apps, schema_editor):
    statements = [
        # Remove admin log rows that reference attendance content types to avoid FK violations
        "DELETE FROM django_admin_log WHERE content_type_id IN (SELECT id FROM django_content_type WHERE app_label = 'attendance');",
        # Remove group_permission rows tied to attendance permissions
        "DELETE FROM auth_group_permissions WHERE permission_id IN (SELECT id FROM auth_permission WHERE content_type_id IN (SELECT id FROM django_content_type WHERE app_label = 'attendance'));",
        # Remove permissions tied to attendance content types
        "DELETE FROM auth_permission WHERE content_type_id IN (SELECT id FROM django_content_type WHERE app_label = 'attendance');",
        # Drop attendance tables (order matters because of FKs)
        "DROP TABLE IF EXISTS attendance_attendanceadjustment CASCADE;",
        "DROP TABLE IF EXISTS attendance_attendance CASCADE;",
        "DROP TABLE IF EXISTS attendance_officenetwork CASCADE;",
        # Finally remove the content types themselves
        "DELETE FROM django_content_type WHERE app_label = 'attendance';",
    ]
    with schema_editor.connection.cursor() as cursor:
        for stmt in statements:
            cursor.execute(stmt)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("employees", "0006_backfill_employees"),
    ]

    operations = [
        migrations.RunPython(drop_attendance_tables, noop),
    ]
