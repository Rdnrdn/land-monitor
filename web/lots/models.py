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


class Subject(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=255)
    okato = models.CharField(max_length=20, blank=True, null=True)
    published = models.BooleanField(blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "subjects"
        ordering = ("code",)

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class Notice(models.Model):
    notice_number = models.TextField(primary_key=True)
    notice_status = models.TextField(blank=True, null=True)
    publish_date = models.DateTimeField(blank=True, null=True)
    create_date = models.DateTimeField(blank=True, null=True)
    update_date = models.DateTimeField(blank=True, null=True)
    bidd_type_code = models.TextField(blank=True, null=True)
    bidd_form_code = models.TextField(blank=True, null=True)
    bidder_org_name = models.TextField(blank=True, null=True)
    right_holder_name = models.TextField(blank=True, null=True)
    auction_site_url = models.TextField(blank=True, null=True)
    auction_site_domain = models.TextField(blank=True, null=True)
    application_portal_url = models.TextField(blank=True, null=True)
    application_portal_domain = models.TextField(blank=True, null=True)
    is_pre_auction = models.BooleanField(blank=True, null=True)
    is_39_18 = models.BooleanField(blank=True, null=True)
    auction_is_electronic = models.BooleanField(blank=True, null=True)
    detected_site_type = models.TextField(blank=True, null=True)
    detected_platform_code = models.TextField(blank=True, null=True)
    is_offline = models.BooleanField(blank=True, null=True)
    raw_data = models.JSONField(blank=True, null=True)
    fetched_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "notices"
        ordering = ("-publish_date", "notice_number")

    def __str__(self) -> str:
        return self.notice_number


class Region(models.Model):
    name = models.CharField(max_length=255)
    slug = models.CharField(max_length=100)
    torgi_region_code = models.IntegerField()
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = "regions"
        ordering = ("sort_order", "name")

    def __str__(self) -> str:
        return self.name


class Municipality(models.Model):
    region = models.ForeignKey(
        Region,
        models.DO_NOTHING,
        db_column="region_id",
        related_name="municipalities",
    )
    name = models.CharField(max_length=255)
    normalized_name = models.CharField(max_length=255)
    slug = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = "municipalities"
        ordering = ("region_id", "sort_order", "name")

    def __str__(self) -> str:
        return self.name


class Lot(models.Model):
    id = models.BigIntegerField(primary_key=True)
    source = models.TextField()
    source_lot_id = models.TextField()
    source_url = models.TextField()
    title = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    region_ref = models.ForeignKey(
        Region,
        models.DO_NOTHING,
        db_column="region_id",
        related_name="lots",
        blank=True,
        null=True,
    )
    subject_ref = models.ForeignKey(
        Subject,
        models.DO_NOTHING,
        db_column="subject_id",
        related_name="lots",
        blank=True,
        null=True,
    )
    municipality_ref = models.ForeignKey(
        Municipality,
        models.DO_NOTHING,
        db_column="municipality_id",
        related_name="lots",
        blank=True,
        null=True,
    )
    region = models.TextField(blank=True, null=True)
    region_name = models.TextField(blank=True, null=True)
    source_torgi_region_code = models.TextField(blank=True, null=True)
    subject_rf_code = models.TextField(blank=True, null=True)
    district = models.TextField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    fias_guid = models.TextField(blank=True, null=True)
    cadastre_number = models.TextField(blank=True, null=True)
    area_m2 = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    category = models.TextField(blank=True, null=True)
    permitted_use = models.TextField(blank=True, null=True)
    ownership_form_code = models.TextField(blank=True, null=True)
    ownership_form_name = models.TextField(blank=True, null=True)
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
    source_notice_bidd_type_code = models.TextField(blank=True, null=True)
    fias_level_3_guid = models.TextField(blank=True, null=True)
    fias_level_3_name = models.TextField(blank=True, null=True)
    fias_level_5_guid = models.TextField(blank=True, null=True)
    fias_level_5_name = models.TextField(blank=True, null=True)
    fias_level_6_guid = models.TextField(blank=True, null=True)
    fias_level_6_name = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(blank=True, null=True)
    is_finished = models.BooleanField(blank=True, null=True)
    application_start_date = models.DateTimeField(blank=True, null=True)
    application_deadline = models.DateTimeField(blank=True, null=True)
    auction_date = models.DateTimeField(blank=True, null=True)
    source_created_at = models.DateTimeField(blank=True, null=True)
    source_updated_at = models.DateTimeField(blank=True, null=True)
    lotcard_enriched_at = models.DateTimeField(blank=True, null=True)
    price_bucket = models.TextField(blank=True, null=True)
    days_to_deadline = models.IntegerField(blank=True, null=True)
    is_price_null = models.BooleanField(blank=True, null=True)
    is_etp_empty = models.BooleanField(blank=True, null=True)
    score = models.IntegerField(blank=True, null=True)
    segment = models.TextField(blank=True, null=True)
    municipality_name = models.TextField(blank=True, null=True)
    raw_data = models.JSONField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "lots"

    def __str__(self) -> str:
        return self.title or f"Lot {self.id}"

    @property
    def region_display(self) -> str | None:
        if self.region_ref_id and self.region_ref:
            return self.region_ref.name
        return self.region_name or self.region


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
