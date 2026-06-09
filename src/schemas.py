from pydantic import BaseModel, Field

class ProductInfo(BaseModel):
    model_number: str
    manufacturer: str
    product_type: str
    country_of_origin: str | None = None
    rated_power_kw: str | None = None
    product_series: str | None = None

class ElectricalSpecs(BaseModel):
    # DC input
    max_dc_input_voltage: str | None = None
    mppt_voltage_range: str | None = None
    max_dc_input_current: str | None = None
    number_of_mppt_trackers: str | None = None

    # AC output
    rated_ac_output_power: str | None = None
    ac_output_voltage: str | None = None
    ac_output_frequency: str | None = None
    max_ac_output_current: str | None = None
    power_factor: str | None = None
    thd_current: str | None = None

    # Efficiency
    peak_efficiency: str | None = None
    euro_efficiency: str | None = None

    additional: dict[str, str] = Field(
        default_factory=dict,
        description="Any other electrical parameters found in the document",
    )

class MechanicalSpecs(BaseModel):
    dimensions_mm: str | None = None
    weight_kg: str | None = None
    cooling_type: str | None = None
    mounting_type: str | None = None
    enclosure_material: str | None = None
    additional: dict[str, str] = Field(
        default_factory=dict,
        description="Any other mechanical specs found in the document",
    )

class EnvironmentalSpecs(BaseModel):
    ip_rating: str | None = None
    operating_temp_range: str | None = None
    storage_temp_range: str | None = None
    max_humidity: str | None = None
    max_altitude_m: str | None = None
    additional: dict[str, str] = Field(
        default_factory=dict,
        description="Any other environmental specs found in the document",
    )

class ProtectionFeatures(BaseModel):
    overvoltage_protection: bool | None = None
    undervoltage_protection: bool | None = None
    overcurrent_protection: bool | None = None
    anti_islanding: bool | None = None
    ground_fault_protection: bool | None = None
    arc_fault_protection: bool | None = None
    additional: list[str] = Field(
        default_factory=list,
        description="Any other protection features mentioned in the document",
    )

class ProductEntry(BaseModel):
    """All specs belonging to a single product / model variant."""

    product_info: ProductInfo
    electrical_specs: ElectricalSpecs
    mechanical_specs: MechanicalSpecs
    environmental_specs: EnvironmentalSpecs
    protection_features: ProtectionFeatures
    communication_interfaces: list[str] = Field(
        default_factory=list,
        description="e.g. RS485, WiFi, Zigbee, Bluetooth, display",
    )
    other_data: dict[str, str] = Field(
        default_factory=dict,
        description="Any product-specific data not captured in the fields above",
    )

class ExtractionResult(BaseModel):
    """
    Top-level result for one document.

    A document may describe a single product or a family of variants (e.g. a
    test report covering 9 power ratings of the same inverter platform).
    Each distinct model gets its own ProductEntry; document-level fields
    (certifications, compliance_standards, other_data) are shared.
    """

    products: list[ProductEntry] = Field(
        description=(
            "One entry per distinct product / model variant found in the document. "
            "If the document covers a single product, this list has exactly one item. "
            "If variants differ only in rated power but share all other specs, still "
            "create a separate entry per model number — do not merge them."
        )
    )

    certifications: list[str] = Field(
        default_factory=list,
        description="All certifications mentioned: IEC, CE, TUV, UL, etc.",
    )
    compliance_standards: dict[str, str] = Field(
        default_factory=dict,
        description="Standard name → compliance status, e.g. {'IEC 62109-1': 'Compliant'}",
    )
    other_data: dict[str, str] = Field(
        default_factory=dict,
        description="Document-level data not tied to any specific product",
    )