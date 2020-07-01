"""Contains the models fro the representation of Anaconda channels."""
from __future__ import annotations
import copy
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Set

from isoconda.errors import InvalidChannel
from isoconda.models.repo import PackageRecord, RepoData
import isoconda.models.utils as utils


class ChannelGroupInfo:
    """Information realted to a group of packages in a Anaconda channel.

    Refers directly to elements in the channeldata.json sub-dictionaries: 'packages'.
    Channel groups are developed for use with the ``conda`` executable. The structure of
    these groups are dictated by the Anaconda organization and therefore are subject to
    change. In order to minimize breaking changes, this class only interacts with a small
    number of records fields and propagates all other fields when saving.
    """

    def __init__(self, name: str, data: Dict[str, Any]):
        """Initialize object instance from record data.

        Args:
            filename: Package filename (on disk or as a download)
            data: Dictionary representation of group info.
        """
        self._name = name
        self._data: Dict[str, Any] = copy.deepcopy(data)
        self._pkey = self._name
        self._hash = hash(self._pkey)

    @property
    def name(self) -> str:
        """The name of the package group."""
        return self._name

    @property
    def timestamp(self) -> Optional[int]:
        """The timestap of the latest package in the group."""
        return self._data.get('timestamp', None)

    @property
    def version(self) -> str:
        """The version of the latest package in the group."""
        return self._data['version']

    def dump(self) -> Dict[str, Any]:
        """Converts data into a dictionary representation."""
        return copy.deepcopy(self._data)

    def update_latest(self, version: str, timestamp: Optional[int] = None) -> ChannelGroupInfo:
        """Create a new object with updated version and timestamp information."""
        data = copy.deepcopy(self._data)
        if timestamp is None or timestamp == 0:
            data.pop('timestamp', None)
        else:
            data['timestamp'] = timestamp
        data['version'] = version
        return type(self)(self.name, data)

    def update_subdirs(self, subdirs: Iterable[str]) -> ChannelGroupInfo:
        """Create a new object with updated sub-directory information."""
        data = copy.deepcopy(self._data)
        data['subdirs'] = list(subdirs)
        return type(self)(self.name, data)

    def __eq__(self, other):
        return self._pkey == other._pkey

    def __hash__(self):
        return self._hash

    def __repr__(self):
        return f'{type(self).__name__}(name={self.name!r}, data={self._data!r})'


class ChannelData(Mapping[str, ChannelGroupInfo]):
    """An Anaconda channel data (channeldata.json) implementing the Mapping protocol.

    The Anaconda channel data contains info on groups of packages in a platfrom
    specific sub-directory.
    """

    VERSION = 1

    def __init__(self, subdirs: Iterable[str], groups: Mapping[str, ChannelGroupInfo]):
        """Initializes data from basic repository components.

        Args:
            subdirs: Iterable of anaconda repository sub-directories (platfrom architecture)
            groups: ``ChannelGroupInfo`` grouped by package type (name).
        """
        self._subdirs: List[str] = list(subdirs)
        self._groups: Dict[str, ChannelGroupInfo] = dict(groups)

    @classmethod
    def from_data(cls, channeldata: Dict[str, Any]) -> ChannelData:
        """Creates an object instance from data within an anaconda channel.

        Args:
            channeldata: Dictionary representation of anaconda channel data.
        """
        # The simplest check of the repodata.json schema version
        repodata_version = channeldata['channeldata_version']
        if repodata_version != cls.VERSION:
            raise InvalidChannel(f'Unknown repodata version: {repodata_version}')

        subdirs = channeldata['subdirs']
        groups: Dict[str, ChannelGroupInfo] = {}

        for name, data in channeldata['packages'].items():
            info = ChannelGroupInfo(name, data)
            groups[info.name] = info

        return cls(subdirs, groups)

    def dump(self) -> Dict[str, Any]:
        """Converts data into a dictionary representation."""
        data: Dict[str, Any] = {}
        data['channeldata_version'] = self.VERSION
        data['packages'] = {name: group.dump() for name, group in self._groups.items()}
        data['subdirs'] = sorted(self.subdirs)
        return data

    def merge(self, other: ChannelData) -> ChannelData:
        """Merges current channels with another repository."""
        subdirs = sorted(set(self.subdirs) | set(other.subdirs))

        groups: Dict[str, ChannelGroupInfo] = {}
        keys = set(self._groups.keys()) | set(other.keys())
        for key in sorted(keys):
            if key in self._groups:
                groups[key] = self._groups[key]
            else:
                groups[key] = other[key]

        return ChannelData(subdirs, groups)

    def rescale(self, repos: Iterable[RepoData]) -> ChannelData:
        """Rescales the current groups in the channel based on given repositories.

        Args:
            repos: An iterable of Anaconda repositories.

        Returns:
            Rescal Anaconda channel.
        """
        channel_subdirs: Set[str] = set()
        groups: Dict[str, ChannelGroupInfo] = {}
        for name, info in self.items():
            packages: List[PackageRecord] = []
            for repo in repos:
                if name in repo:
                    packages.extend(repo[name])
                    channel_subdirs.add(repo.subdir)
            if packages:
                # Update the subdirs and the most recent version / timestamp combination
                subdirs = sorted({package.subdir for package in packages})
                order, timestamp = max((utils.create_order(package.version), package.timestamp)
                                       for package in packages)
                modified_info = info.update_subdirs(subdirs).update_latest(str(order), timestamp)
                groups[name] = modified_info
        return type(self)(channel_subdirs, groups)

    @property
    def subdirs(self) -> List[str]:
        """Repository sub-directories (platfrom architecture)."""
        return self._subdirs.copy()

    def __contains__(self, key) -> bool:
        return key in self._groups.keys()

    def __getitem__(self, key) -> ChannelGroupInfo:
        return self._groups[key]

    def __iter__(self) -> Iterator[str]:
        yield from self._groups.keys()

    def __len__(self) -> int:
        return len(self._groups.keys())

    def __repr__(self) -> str:
        return f"{type(self).__name__}(subdirs=[{','.join(self.subdirs)!r}], groups=...)"