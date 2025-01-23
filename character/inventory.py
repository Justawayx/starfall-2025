import math
from typing import cast

import disnake
from tortoise.expressions import F

from utils.Database import AllRings, Inventory, RingInventory
from utils.InventoryUtils import combine_id, convert_id, ConfirmDelete
from utils.base import singleton
from world.compendium import ItemCompendium, ItemDefinition, StorageRingDefinition, CauldronDefinition

BASE_INV_CAPACITY = 80


class Item:
    def __init__(self, definition: ItemDefinition | StorageRingDefinition | CauldronDefinition, unique_id: int, quantity: int):
        self._definition = definition
        self._unique_id = unique_id
        self._quantity = quantity

    def __repr__(self):
        return f"id:{self._definition.item_id}/{self._unique_id}, count:{self._quantity}"

    def __eq__(self, other):
        return other is not None and isinstance(other, Item) and self._definition.item_id == other.item_id and self._unique_id == other.unique_id

    @property
    def full_id(self) -> str:
        return combine_id(self._definition.item_id, self._unique_id)

    @property
    def item_id(self) -> str:
        return self._definition.item_id

    @property
    def unique_id(self) -> int:
        return self._unique_id

    @property
    def quantity(self) -> int:
        return self._quantity

    @quantity.setter
    def quantity(self, value):
        self._quantity = value

    @property
    def definition(self) -> ItemDefinition:
        return self._definition


class Cauldron(Item):
    def __init__(self, definition: CauldronDefinition, unique_id: int, cooldown_reduction: int, refine_bonus: int):
        super().__init__(definition, unique_id, 1)
        self._cooldown_reduction = cooldown_reduction
        self._refine_bonus = refine_bonus

    @property
    def cooldown_reduction(self) -> int:
        return self._cooldown_reduction

    @property
    def refine_bonus(self) -> int:
        return self._refine_bonus

    @property
    def definition(self) -> CauldronDefinition:
        return self._definition


class BaseInventory:
    def __init__(self, max_weight: int = BASE_INV_CAPACITY):
        self._items: dict[str, Item] = {}
        self._max_weight: int = max_weight

    def __contains__(self, item: str) -> bool:
        return item in self._items.keys()

    def __getitem__(self, full_id: str) -> Item | None:
        return self.items.get(full_id, None)

    def __len__(self) -> int:
        return len(self._items.keys())

    @property
    def items(self) -> dict[str, Item]:
        return self._items.copy()

    @property
    def current_weight(self) -> int:
        return sum([item.definition.weight for item in self._items.values()])

    @property
    def max_weight(self) -> int:
        return self._max_weight

    @property
    def as_list(self) -> list[Item]:
        return list(self._items.values())

    def add(self, item: Item) -> None:
        if item.full_id not in self._items.keys():
            self._items[item.full_id] = item

    def remove(self, item: Item) -> None:
        if item.full_id in self._items.keys():
            self._items.pop(item.full_id)


class StorageRing(Item, BaseInventory):
    def __init__(self, definition: ItemDefinition, unique_id: int):
        Item.__init__(self, definition, unique_id, 1)
        BaseInventory.__init__(self, self.weight_capacity)

    @property
    def definition(self) -> StorageRingDefinition:
        return cast(StorageRingDefinition, super().definition)

    @property
    def ring(self) -> StorageRingDefinition:
        return cast(StorageRingDefinition, self.definition)

    @property
    def weight_capacity(self) -> int:
        return self.definition.weight_capacity


@singleton
class RingStorage:
    def __init__(self):
        self._rings: dict[int, StorageRing] = {}

    def __getitem__(self, item: int) -> StorageRing | None:
        return self._rings.get(item, None)

    def __iter__(self) -> list[StorageRing]:
        return list(self._rings.values())

    def __repr__(self):
        return f"Total Rings: {len(self._rings)}"

    def __str__(self):
        return self.__repr__()

    @property
    def all(self) -> dict[int, StorageRing]:
        return self._rings.copy()

    @property
    def as_list(self) -> list[StorageRing]:
        return self.__iter__()

    async def load(self):
        all_rings = await AllRings.all().values_list("id", "ring")
        for ring in all_rings:
            _id, ring_id = ring
            r = StorageRing(ItemCompendium().get(ring_id), _id)
            self.add(r)

    def add(self, item: StorageRing) -> None:
        if item.unique_id not in self._rings.keys():
            self._rings[item.unique_id] = item

    def remove(self, item: StorageRing) -> None:
        if item.unique_id in self._rings.keys():
            self._rings.pop(item.unique_id)


class PlayerInventory:
    def __init__(self, user_id: int, base_inventory: BaseInventory, equipped_ring: StorageRing | None):
        self._user_id = user_id
        self._base = base_inventory
        self._equipped_ring = equipped_ring
        self._all_rings: list[StorageRing] = [ring for ring in base_inventory.as_list if isinstance(ring, StorageRing)]

    def __repr__(self):
        pass

    def __str__(self):
        return self.__repr__()

    @property
    def base(self) -> BaseInventory:
        return self._base

    @property
    def ring(self) -> StorageRing | None:
        return self._equipped_ring

    @property
    def all_rings(self) -> list[StorageRing]:
        return self._all_rings

    @property
    def all_rings_id(self) -> list[int]:
        return [ring.unique_id for ring in self._all_rings]

    def _combine_inv(self, as_str: bool = False) -> list[Item | StorageRing | Cauldron | str]:
        items = self._base.as_list
        items.extend(self.ring.as_list)
        if as_str:
            items = [i.full_id for i in items]
            return items

        return items

    async def create_ring(self, ring: StorageRingDefinition, unique_id, ignore_weight: bool = False) -> StorageRing:
        new_ring = StorageRing(ring, unique_id)
        if len(self._all_rings) > 5 and ignore_weight is False:
            if (self.base.max_weight - self.base.current_weight) >= new_ring.definition.weight:
                self._all_rings.append(new_ring)
                self.base.add(new_ring)
                await Inventory.create(item_id=new_ring.item_id, user_id=self._user_id, count=new_ring.quantity, unique_id=new_ring.unique_id)
            else:
                pass
        else:
            self._all_rings.append(new_ring)
            self.base.add(new_ring)
            await Inventory.create(item_id=new_ring.item_id, user_id=self._user_id, count=new_ring.quantity, unique_id=new_ring.unique_id)

        return new_ring

    def check_item_in_inv(self, full_id: str, quantity: int = 1) -> bool:
        inv = self._combine_inv()
        for i in inv:
            if full_id == i.full_id:
                if quantity <= i.quantity:
                    return True

        return False

    async def check_inv_weight(self, full_id: str, quantity: int = 1, ring_only: bool = True, send_prompt: bool = True, prompt_text: str = None, channel: disnake.TextChannel = None) -> bool:
        item_id, unique_id = convert_id(full_id)
        item_def = ItemCompendium().get(item_id)
        if self.ring:
            if (self.ring.max_weight - self.ring.current_weight) >= (item_def.weight * quantity):
                return True

        if ring_only is False:
            if (self.base.max_weight - self.base.current_weight) >= (item_def.weight * quantity):
                return True

        if send_prompt and channel is not None:
            view = ConfirmDelete(self._user_id)
            if prompt_text:
                await channel.send(prompt_text, view=view)
            else:
                await channel.send(f"Your inventory is full, and you may lose the item ({quantity}x {item_id}). Continue?", view=view)
            await view.wait()
            return view.confirm

        return False

    async def add_item(self, full_id: str, quantity: int = 1, add_to_ring: bool = True) -> None:
        item_id, unique_id = convert_id(full_id)
        quantity_left = quantity
        if add_to_ring and self.ring:
            item_in_ring = self.ring[full_id]

            if item_in_ring is not None:
                if (self.ring.max_weight - self.ring.current_weight) < (item_in_ring.definition.weight * quantity_left):
                    quantity_left = math.floor(self.ring.current_weight / item_in_ring.definition.weight)

                if quantity_left > 0:
                    item_in_ring.quantity += quantity_left
                    await RingInventory.filter(item_id=item_id, unique_id=unique_id, user_id=self._user_id).update(count=F("count") + quantity_left)
            else:
                item_def = ItemCompendium().get(item_id)

                if (self.ring.max_weight - self.ring.current_weight) < (item_def.weight * quantity_left):
                    quantity_left = math.floor(self.ring.current_weight / item_def.weight)

                if quantity_left > 0:
                    new_item = Item(item_def, int(unique_id), quantity_left)
                    self.ring.add(new_item)
                    await RingInventory.create(item_id=new_item.item_id, user_id=self._user_id, count=new_item.quantity, unique_id=new_item.unique_id)

        else:
            item_in_base = self.base[full_id]
            if item_in_base is not None:
                item_in_base.quantity += quantity_left
                await Inventory.filter(item_id=item_id, user_id=self._user_id).update(count=F("count") + quantity_left)
            else:
                new_item = Item(ItemCompendium().get(item_id), int(unique_id), quantity_left)
                self.base.add(new_item)
                await Inventory.create(item_id=new_item.item_id, user_id=self._user_id, count=new_item.quantity, unique_id=new_item.unique_id)

    async def remove_item(self, full_id: str, quantity: int = 1, remove_from_ring: bool = True) -> None:
        item_id, unique_id = convert_id(full_id)
        total_quantity = quantity

        if remove_from_ring and self.ring:
            item_in_ring = self.ring[full_id]

            if item_in_ring is not None:
                ring_item_quantity = item_in_ring.quantity
                ring_buffer = ring_item_quantity - total_quantity

                if ring_buffer > 0:
                    item_in_ring.quantity -= total_quantity
                    await RingInventory.filter(ring_id=self.ring.unique_id, item_id=item_id, unique_id=unique_id).update(count=F("count") - total_quantity)

        if total_quantity > 0:
            item_in_base = self.base[full_id]

            if item_in_base is not None:
                base_item_quantity = item_in_base.quantity
                base_buffer = base_item_quantity - total_quantity

                if base_buffer > 0:
                    item_in_base.quantity -= quantity
                    await Inventory.filter(item_id=item_id, user_id=self._user_id, unique_id=unique_id).update(count=F("count") - total_quantity)

                elif base_buffer == 0:
                    self.base.remove(item_in_base)
                    await Inventory.filter(item_id=item_id, user_id=self._user_id, unique_id=unique_id).delete()

                elif base_buffer <= 0:
                    self.ring.remove(item_in_base)
                    await RingInventory.filter(ring_id=self.ring.unique_id, item_id=item_id, unique_id=unique_id).delete()
