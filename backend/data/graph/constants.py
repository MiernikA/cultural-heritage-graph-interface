RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"

CIDOC = "http://www.cidoc-crm.org/cidoc-crm/"
UJ = "http://onto.uj.edu.pl#"

P102_HAS_TITLE = CIDOC + "P102_has_title"
P1I_IDENTIFIES = CIDOC + "P1i_identifies"
P4I_IS_TIME_SPAN_OF = CIDOC + "P4i_is_time-span_of"
P82A_BEGIN = CIDOC + "P82a_begin_of_the_begin"
P82B_END = CIDOC + "P82b_end_of_the_end"
P11_HAD_PARTICIPANT = CIDOC + "P11_had_participant"
P11I_PARTICIPATED_IN = CIDOC + "P11i_participated_in"
P14_CARRIED_OUT_BY = CIDOC + "P14_carried_out_by"
P14I_PERFORMED = CIDOC + "P14i_performed"
P108_HAS_PRODUCED = CIDOC + "P108_has_produced"
P102I_IS_TITLE_OF = CIDOC + "P102i_is_title_of"
P94_HAS_CREATED = CIDOC + "P94_has_created"
P128_CARRIES = CIDOC + "P128_carries"
P129I_IS_SUBJECT_OF = CIDOC + "P129i_is_subject_of"
P100_WAS_DEATH_OF = CIDOC + "P100_was_death_of"
P98_BROUGHT_INTO_LIFE = CIDOC + "P98_brought_into_life"
P2I_IS_TYPE_OF = CIDOC + "P2i_is_type_of"
P7I_WITNESSED = CIDOC + "P7i_witnessed"
P14_1_IN_ROLE = CIDOC + "P14.1_in_the_role_of"
P01_HAS_DOMAIN = CIDOC + "P01_has_domain"
P02_HAS_RANGE = CIDOC + "P02_has_range"

E35_TITLE = CIDOC + "E35_Title"
E41_APPELLATION = CIDOC + "E41_Appellation"
E67_BIRTH = CIDOC + "E67_Birth"
E69_DEATH = CIDOC + "E69_Death"
E12_PRODUCTION = CIDOC + "E12_Production"
E65_CREATION = CIDOC + "E65_Creation"
E33_LINGUISTIC_OBJECT = CIDOC + "E33_Linguistic_Object"

TECHNICAL_TYPES = {
    E35_TITLE,
    E41_APPELLATION,
    E67_BIRTH,
    E69_DEATH,
    E12_PRODUCTION,
    E33_LINGUISTIC_OBJECT,
    E65_CREATION,
    CIDOC + "PC14_carried_out_by",
}
