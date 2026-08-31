# SOFTI-MEJORA — fork models (upstream + must_change_password en EUsers)
# Tablas reales: e_domains, e_users, etc.

from django.db import models
from websiteFunctions.models import Websites, ChildDomains


class Domains(models.Model):
    domainOwner = models.ForeignKey(Websites, on_delete=models.CASCADE, null=True)
    childOwner = models.ForeignKey(ChildDomains, on_delete=models.CASCADE, null=True)
    domain = models.CharField(primary_key=True, max_length=50)

    class Meta:
        db_table = 'e_domains'


class EUsers(models.Model):
    emailOwner = models.ForeignKey(Domains, on_delete=models.CASCADE)
    email = models.CharField(primary_key=True, max_length=80)
    password = models.CharField(max_length=200)
    mail = models.CharField(max_length=200, default='')
    DiskUsage = models.CharField(max_length=200, default='0')
    # SOFTI-MEJORA — forzar cambio de contraseña en primer login a SnappyMail
    must_change_password = models.BooleanField(default=False)

    class Meta:
        db_table = 'e_users'


class Forwardings(models.Model):
    source = models.CharField(max_length=80)
    destination = models.TextField()

    class Meta:
        db_table = 'e_forwardings'


class Transport(models.Model):
    domain = models.CharField(unique=True, max_length=128)
    transport = models.CharField(max_length=128)

    class Meta:
        db_table = 'e_transport'


class Pipeprograms(models.Model):
    source = models.CharField(max_length=80)
    destination = models.TextField()

    class Meta:
        db_table = 'e_pipeprograms'


class CatchAllEmail(models.Model):
    domain = models.OneToOneField(
        Domains, on_delete=models.CASCADE, primary_key=True, db_column='domain_id'
    )
    destination = models.CharField(max_length=255)
    enabled = models.BooleanField(default=True)

    class Meta:
        db_table = 'e_catchall'
        managed = False


class EmailServerSettings(models.Model):
    plus_addressing_enabled = models.BooleanField(default=False)
    plus_addressing_delimiter = models.CharField(max_length=1, default='+')

    class Meta:
        db_table = 'e_server_settings'
        managed = False

    @classmethod
    def get_settings(cls):
        settings, _ = cls.objects.get_or_create(pk=1)
        return settings
