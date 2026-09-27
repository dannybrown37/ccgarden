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


REAL_USAGE = {
    label: len(REAL_COMBOS) - i for i, label in enumerate(REAL_COMBOS)
}


class TestAssignSpecies:
    def test_every_real_combo_gets_its_own_plant(self):
        mapping = assign_species(REAL_USAGE)
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
        assert assign_species(REAL_USAGE)[label] in FAMILY_POOLS[family]

    @pytest.mark.parametrize(
        ('busiest', 'runner_up', 'family'),
        [
            ('claude-opus-4-6 (low)', 'claude-opus-5 (low)', 'opus'),
            ('claude-sonnet-5 (low)', 'claude-sonnet-5 (medium)', 'sonnet'),
            ('claude-haiku-4-5 (low)', 'claude-haiku-4-5 (high)', 'haiku'),
        ],
    )
    def test_pool_order_follows_usage(self, busiest, runner_up, family):
        mapping = assign_species({runner_up: 5, busiest: 50})
        assert mapping[busiest] == FAMILY_POOLS[family][0]
        assert mapping[runner_up] == FAMILY_POOLS[family][1]

    def test_usage_tie_is_broken_by_label(self):
        mapping = assign_species(
            {'claude-opus-5 (low)': 3, 'claude-opus-4-6 (low)': 3}
        )
        assert mapping['claude-opus-4-6 (low)'] == FAMILY_POOLS['opus'][0]
        assert mapping['claude-opus-5 (low)'] == FAMILY_POOLS['opus'][1]

    def test_unknown_model_is_a_sprout(self):
        assert assign_species({'<synthetic>': 1})['<synthetic>'] == 'sprout'

    def test_order_of_input_does_not_matter(self):
        assert assign_species(REAL_USAGE) == assign_species(
            dict(reversed(REAL_USAGE.items()))
        )

    def test_more_combos_than_plants_still_assigns(self):
        many = {f'claude-haiku-{i} (low)': i for i in range(12)}
        mapping = assign_species(many)
        assert set(mapping) == set(many)
        assert set(mapping.values()) <= set(FAMILY_POOLS['haiku'])

    def test_empty(self):
        assert assign_species({}) == {}


class TestCatalog:
    def test_every_pooled_species_is_drawn(self):
        pooled = {s for pool in FAMILY_POOLS.values() for s in pool}
        assert pooled <= set(SPECIES)

    @pytest.mark.parametrize('name', sorted(SPECIES))
    def test_species_is_tinted_by_current_color(self, name):
        assert 'currentColor' in SPECIES[name].body

    @pytest.mark.parametrize(
        ('name', 'family'),
        [('cabbage', 'sonnet'), ('kale', 'sonnet'), ('melon', 'opus')],
    )
    def test_plant_sits_in_its_family(self, name, family):
        homes = [f for f, pool in FAMILY_POOLS.items() if name in pool]
        assert homes == [family]

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
        assert 'tomato' not in assign_species(REAL_USAGE).values()
