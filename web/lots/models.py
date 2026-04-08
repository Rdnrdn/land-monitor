from django.db import models


class UserLotStatus(models.TextChoices):
    NEW = "NEW", "NEW"
    REVIEW = "REVIEW", "REVIEW"
    PLAN = "PLAN", "PLAN"
    APPLIED = "APPLIED", "APPLIED"
    BIDDING = "BIDDING", "BIDDING"
    WON = "WON", "WON"
    LOST = "LOST", "LOST"
    SKIPPED = "SKIPPED", "SKIPPED"
    ARCHIVE = "ARCHIVE", "ARCHIVE"


class Lot(models.Model):
    id = models.BigIntegerField(primary_key=True)
    source = models.TextField()
    source_lot_id = models.TextField()
    source_url = models.TextField()
    title = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    region = models.TextField(blank=True, null=True)
    district = models.TextField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    fias_guid = models.TextField(blank=True, null=True)
    cadastre_number = models.TextField(blank=True, null=True)
    area_m2 = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    category = models.TextField(blank=True, null=True)
    permitted_use = models.TextField(blank=True, null=True)
    price_min = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    price_fin = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    deposit_amount = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    currency_code = models.TextField(blank=True, null=True)
    etp_code = models.TextField(blank=True, null=True)
    etp_name = models.TextField(blank=True, null=True)
    organizer_name = models.TextField(blank=True, null=True)
    organizer_inn = models.TextField(blank=True, null=True)
    organizer_kpp = models.TextField(blank=True, null=True)
    lot_status_external = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(blank=True, null=True)
    is_finished = models.BooleanField(blank=True, null=True)
    application_start_date = models.DateTimeField(blank=True, null=True)
    application_deadline = models.DateTimeField(blank=True, null=True)
    auction_date = models.DateTimeField(blank=True, null=True)
    source_created_at = models.DateTimeField(blank=True, null=True)
    source_updated_at = models.DateTimeField(blank=True, null=True)
    price_bucket = models.TextField(blank=True, null=True)
    days_to_deadline = models.IntegerField(blank=True, null=True)
    is_price_null = models.BooleanField(blank=True, null=True)
    is_etp_empty = models.BooleanField(blank=True, null=True)
    score = models.IntegerField(blank=True, null=True)
    segment = models.TextField(blank=True, null=True)
    raw_data = models.JSONField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "lots"

    def __str__(self) -> str:
        return self.title or f"Lot {self.id}"


class UserLot(models.Model):
    id = models.UUIDField(primary_key=True)
    lot = models.OneToOneField(
        Lot,
        models.DO_NOTHING,
        db_column="lot_id",
        related_name="user_lot",
    )
    user_status = models.CharField(
        max_length=20,
        choices=UserLotStatus.choices,
        default=UserLotStatus.NEW,
    )
    is_favorite = models.BooleanField(default=False)
    needs_inspection = models.BooleanField(default=False)
    needs_legal_check = models.BooleanField(default=False)
    deposit_paid = models.BooleanField(default=False)
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "user_lots"

    def __str__(self) -> str:
        return f"{self.get_user_status_display()} for lot {self.lot_id}"
