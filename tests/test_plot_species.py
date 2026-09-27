"""Tests for the plot's plant catalog and combo → species assignment."""

from __future__ import annotations

import pytest

from ccgarden.plot_species import (
    FAMILY_POOLS,
    SPECIES,
    assign_species,
    combo_name,
)

REAL_COMBOS = [
    'claude-opus-4-6 (low)',
    'claude-sonnet-5 (low)',
    'claude-opus-5 (low)',
    'claude-opus-4-6 (medium)',
    'claude-opus-4-6 (high)',
    'claude-sonnet-5 (medium)',
    'claude-sonnet-5 (high)',
    'claude-opus-5 (medium)',
    'claude-haiku-4-5-20251001',
    'claude-opus-5-5 (medium)',
    'claude-sonnet-5 (xhigh)',
    'claude-opus-4-7 (high)',
    '<synthetic>',
    'claude-opus-4-7 (low)',
    'claude-opus-5 (xhigh)',
]


class TestAssignSpecies:
    def test_every_real_combo_gets_its_own_plant(self):
        mapping = assign_species(REAL_COMBOS)
        assert set(mapping) == set(REAL_COMBOS)
        assert len(set(mapping.values())) == len(REAL_COMBOS)

    @pytest.mark.parametrize(
        ('label', 'family'),
        [
            ('claude-opus-4-6 (low)', 'opus'),
            ('claude-sonnet-5 (high)', 'sonnet'),
            ('claude-haiku-4-5-20251001', 'haiku'),
        ],
    )
    def test_species_comes_from_the_family_pool(self, label, family):
        assert assign_species(REAL_COMBOS)[label] in FAMILY_POOLS[family]

    def test_unknown_model_is_a_sprout(self):
        assert assign_species(['<synthetic>'])['<synthetic>'] == 'sprout'

    def test_order_of_input_does_not_matter(self):
        assert assign_species(REAL_COMBOS) == assign_species(
            list(reversed(REAL_COMBOS))
        )

    def test_a_combo_keeps_its_plant_when_it_has_the_garden_alone(self):
        full = assign_species(REAL_COMBOS)
        alone = assign_species(['claude-opus-5 (low)'])
        assert alone['claude-opus-5 (low)'] == full['claude-opus-5 (low)']

    def test_more_combos_than_plants_still_assigns(self):
        many = [f'claude-haiku-{i} (low)' for i in range(12)]
        mapping = assign_species(many)
        assert set(mapping) == set(many)
        assert set(mapping.values()) <= set(FAMILY_POOLS['haiku'])

    def test_empty(self):
        assert assign_species([]) == {}


class TestCatalog:
    def test_every_pooled_species_is_drawn(self):
        pooled = {s for pool in FAMILY_POOLS.values() for s in pool}
        assert pooled <= set(SPECIES)

    @pytest.mark.parametrize('name', sorted(SPECIES))
    def test_species_is_tinted_by_current_color(self, name):
        assert 'currentColor' in SPECIES[name].body

    def test_pools_never_share_a_plant(self):
        pools = list(FAMILY_POOLS.values())
        for i, a in enumerate(pools):
            for b in pools[i + 1 :]:
                assert not set(a) & set(b)


class TestComboName:
    @pytest.mark.parametrize(
        ('label', 'expected'),
        [
            ('claude-opus-4-6 (low)', 'Opus 4.6 · low'),
            ('claude-sonnet-5 (xhigh)', 'Sonnet 5 · xhigh'),
            ('claude-opus-5-5 (medium)', 'Opus 5.5 · medium'),
            ('claude-haiku-4-5-20251001', 'Haiku 4.5'),
            ('<synthetic>', 'synthetic'),
        ],
    )
    def test_readable(self, label, expected):
        assert combo_name(label) == expected


class TestNoTomatoes:
    def test_tomato_is_not_in_the_catalog(self):
        assert 'tomato' not in SPECIES
        assert all('tomato' not in pool for pool in FAMILY_POOLS.values())

    def test_no_combo_grows_a_tomato(self):
        assert 'tomato' not in assign_species(REAL_COMBOS).values()
