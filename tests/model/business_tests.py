# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from google.appengine.api import memcache
from google.appengine.ext import ndb
from gaebusiness.business import CommandExecutionException, Command, CommandSequential

from gaeforms.ndb.form import ModelForm
from gaegraph.business_base import NodeSearch, DestinationsSearch, OriginsSearch, SingleDestinationSearch, \
    SingleOriginSearch, UpdateNode, DeleteNode, DeleteArcs, ArcSearch, CreateArc, CreateSingleArc, HasArcCommand, \
    CreateUniqueArc, CreateSingleOriginArc, CreateSingleDestinationArc
from gaegraph.model import Node, Arc, destinations_cache_key, origins_cache_key, to_node_key
from model.util import GAETestCase
from mommygae import mommy


class NodeAccessTests(GAETestCase):
    def test_execution(self):
        node_search = NodeSearch("1")
        node_search.execute()
        self.assertIsNone(node_search.result)
        node_key = Node(id=1).put()
        node_search.execute()
        self.assertEqual(node_key, node_search.result.key)

    def test_error_when_node_is_not_class_instance(self):
        class SpecificNode(Node):
            pass

        class SpecificNodeSearch(NodeSearch):
            _model_class = SpecificNode

        node = mommy.save_one(Node)

        specific_node = mommy.save_one(SpecificNode)

        specific_node_search = SpecificNodeSearch(specific_node)
        self.assertEqual(specific_node, specific_node_search())

        specific_node_search = SpecificNodeSearch(node)
        self.assertRaises(CommandExecutionException, specific_node_search)
        expected_error = {'node_error': '%s should be %s instance' % (node.key, SpecificNode.__name__)}
        self.assertDictEqual(expected_error, specific_node_search.errors)

    def test_none(self):
        class DefinedClassNodeSearch(NodeSearch):
            _model_class = Node

        result = DefinedClassNodeSearch('1')()
        self.assertIsNone(result)


class ArcDestinationsSearch(DestinationsSearch):
    arc_class = Arc


class ArcOriginsSearch(OriginsSearch):
    arc_class = Arc


class SingleDestinationArcSearch(SingleDestinationSearch):
    arc_class = Arc


class SingleOriginArcSearch(SingleOriginSearch):
    arc_class = Arc


class ArcSearchTests(GAETestCase):
    def test_destinations_search(self):
        origin = Node()
        destinations = [Node() for i in xrange(3)]
        ndb.put_multi([origin] + destinations)
        arcs = [Arc(origin=origin.key, destination=d.key) for d in destinations]
        ndb.put_multi(arcs)
        search = ArcDestinationsSearch(origin)
        search.execute()
        expected_keys = [n.key for n in destinations]
        actual_keys = [n.key for n in search.result]
        self.assertItemsEqual(expected_keys, actual_keys)
        cache_keys = memcache.get(destinations_cache_key(Arc, origin))
        self.assertItemsEqual(expected_keys, cache_keys)

        # Assert Arcs are removed from cache
        Arc(origin=origin.key, destination=destinations[0].key).put()
        self.assertIsNone(memcache.get(destinations_cache_key(Arc, origin)))

    def test_origins_search(self):
        destination = Node()
        origins = [Node() for i in xrange(3)]
        ndb.put_multi([destination] + origins)
        arcs = [Arc(origin=ori.key, destination=destination.key) for ori in origins]
        ndb.put_multi(arcs)
        search = ArcOriginsSearch(destination)
        search.execute()
        expected_keys = [n.key for n in origins]
        actual_keys = [n.key for n in search.result]
        self.assertItemsEqual(expected_keys, actual_keys)
        cache_keys = memcache.get(origins_cache_key(Arc, destination))
        self.assertItemsEqual(expected_keys, cache_keys)

        # Assert Arcs are removed from cache
        Arc(origin=origins[0].key, destination=destination.key).put()
        self.assertIsNone(memcache.get(origins_cache_key(Arc, destination)))

    def test_single_destination_search(self):
        destination = Node()
        origin = Node()
        ndb.put_multi([destination, origin])
        search = SingleDestinationArcSearch(origin).execute()
        self.assertIsNone(search.result)
        Arc(origin=origin, destination=destination).put()
        search = SingleDestinationArcSearch(origin).execute()
        self.assertEqual(destination.key, search.result.key)

    def test_single_origin_search(self):
        destination = Node()
        origin = Node()
        ndb.put_multi([destination, origin])
        search = SingleOriginArcSearch(destination).execute()
        self.assertIsNone(search.result)
        Arc(origin=origin, destination=destination).put()
        search = SingleOriginArcSearch(destination)
        search()
        self.assertEqual(origin.key, search.result.key)


class NodeStub(Node):
    name = ndb.StringProperty(required=True)
    age = ndb.IntegerProperty(required=True)


class NodeForm(ModelForm):
    _model_class = NodeStub
    _include = [NodeStub.name, NodeStub.age]


class UpdateNodeStub(UpdateNode):
    _model_form_class = NodeForm


class GaeBusinessCommandsShortcutsTests(GAETestCase):
    def test_update_node_creating_node_key(self):
        node = mommy.save_one(NodeStub)
        self.assertEqual(node, UpdateNodeStub(node).model_key)
        self.assertEqual(node.key, UpdateNodeStub(node.key).model_key)
        self.assertEqual(node.key, UpdateNodeStub(node.key.id()).model_key)
        self.assertEqual(node.key, UpdateNodeStub(unicode(node.key.id())).model_key)

    def test_delete_node_creating_node_key(self):
        nodes = [mommy.save_one(NodeStub) for i in range(3)]
        node_keys = tuple(n.key for n in nodes)
        self.assertTupleEqual(node_keys, DeleteNode(*node_keys).model_keys)
        self.assertTupleEqual(node_keys, DeleteNode(*[k.id() for k in node_keys]).model_keys)
        self.assertTupleEqual(node_keys, DeleteNode(*[unicode(k.id()) for k in node_keys]).model_keys)
        self.assertTupleEqual(node_keys, DeleteNode(*nodes).model_keys)


class SeachArcsTests(GAETestCase):
    def test_both_nodes_none_error(self):
        self.assertRaises(Exception, ArcSearch(Arc), )


class DeleteArcsExample(DeleteArcs):
    arc_class = Arc


class DeleteArcTests(GAETestCase):
    def test_delete_destination_arcs(self):
        self.maxDiff = None
        origin = mommy.save_one(Node)
        destinations = [mommy.save_one(Node) for i in range(5)]
        arcs = [Arc(origin, d) for d in destinations]
        for a in arcs:
            a.put()
        # using search to test cache
        destination_search_cmd = ArcDestinationsSearch(origin)
        self.assertListEqual(destinations, destination_search_cmd())
        single_origin_search = SingleOriginArcSearch(destinations[-1])
        self.assertEqual(origin, single_origin_search())
        DeleteArcsExample(origin, destinations[-1])()

        destination_search_cmd = ArcDestinationsSearch(origin)
        self.assertListEqual(destinations[:-1], destination_search_cmd())
        single_origin_search = SingleOriginArcSearch(destinations[-1])
        self.assertIsNone(single_origin_search())

        single_origin_search = SingleOriginArcSearch(destinations[1])
        self.assertEqual(origin, single_origin_search())

        origins_search = ArcOriginsSearch(destinations[1])
        self.assertListEqual([origin], origins_search())

        DeleteArcsExample(origin)()

        destination_search_cmd = ArcDestinationsSearch(origin)
        self.assertListEqual([], destination_search_cmd())
        single_origin_search = SingleOriginArcSearch(destinations[-1])
        self.assertIsNone(single_origin_search())
        single_origin_search = SingleOriginArcSearch(destinations[1])
        self.assertIsNone(single_origin_search())

        origins_search = ArcOriginsSearch(destinations[1])
        self.assertListEqual([], origins_search())


    def test_delete_origin_arcs(self):
        self.maxDiff = None
        destination = mommy.save_one(Node)
        origins = [mommy.save_one(Node) for i in range(5)]
        arcs = [Arc(o, destination) for o in origins]
        for a in arcs:
            a.put()
        # using search to test cache
        origin_search_cmd = ArcOriginsSearch(destination)
        self.assertListEqual(origins, origin_search_cmd())
        single_destination_search = SingleDestinationArcSearch(origins[-1])
        self.assertEqual(destination, single_destination_search())
        DeleteArcsExample(origins[-1], destination)()

        origin_search_cmd = ArcOriginsSearch(destination)
        self.assertListEqual(origins[:-1], origin_search_cmd())
        single_destination_search = SingleDestinationArcSearch(origins[-1])
        self.assertIsNone(single_destination_search())

        single_destination_search = SingleDestinationArcSearch(origins[1])
        self.assertEqual(destination, single_destination_search())
        destinations_search = ArcDestinationsSearch(origins[1])
        self.assertListEqual([destination], destinations_search())

        # erasing all arcs poiting to destination
        DeleteArcsExample(destination=destination)()

        origin_search_cmd = ArcOriginsSearch(destination)
        self.assertListEqual([], origin_search_cmd())
        single_destination_search = SingleDestinationArcSearch(origins[-1])
        self.assertIsNone(single_destination_search())

        single_destination_search = SingleDestinationArcSearch(origins[1])
        self.assertIsNone(single_destination_search())

        destinations_search = ArcDestinationsSearch(origins[1])
        self.assertListEqual([], destinations_search())


class CreateArcExample(CreateArc):
    arc_class = Arc


class CreateSingleArcExample(CreateSingleArc):
    arc_class = Arc


class CreateArcTests(GAETestCase):
    def test_create_arc_with_nodes(self):
        destination = mommy.save_one(Node)
        origin = mommy.save_one(Node)
        cmd = CreateArcExample(origin, destination)
        self.assert_arc_creation(cmd, origin, destination)

    def test_create_arc_with_id(self):
        destination = mommy.save_one(Node)
        origin = mommy.save_one(Node)
        cmd = CreateArcExample(origin, str(destination.key.id()))
        self.assert_arc_creation(cmd, origin, destination)

    def test_create_arc_with_none(self):
        origin = mommy.save_one(Node)
        cmd = CreateArcExample(origin, None)
        self.assertRaises(CommandExecutionException, cmd)

    def test_create_arc_with_invalid_id(self):
        origin = mommy.save_one(Node)
        cmd = CreateArcExample(origin, '')
        self.assertRaises(CommandExecutionException, cmd)

    def test_create_arc_with_key(self):
        destination = mommy.save_one(Node)
        origin = mommy.save_one(Node)
        cmd = CreateArcExample(origin, destination.key)
        self.assert_arc_creation(cmd, origin, destination)

    def test_create_arc_with_commands(self):
        destination = mommy.save_one(Node)
        origin = mommy.save_one(Node)

        cmd = CreateArcExample(NodeSearch(origin), destination)
        self.assert_arc_creation(cmd, origin, destination)

        cmd = CreateArcExample(origin, NodeSearch(destination))
        self.assert_arc_creation(cmd, origin, destination)

        cmd = CreateArcExample(NodeSearch(origin), NodeSearch(destination))
        self.assert_arc_creation(cmd, origin, destination)

    def test_create_single_arc(self):
        destination = mommy.save_one(Node)
        origin = mommy.save_one(Node)
        cmd = CreateSingleArcExample(origin, destination)
        self.assert_arc_creation(cmd, origin, destination)


    def test_create_single_arc_for_second_time_error(self):
        destination = mommy.save_one(Node)
        origin = mommy.save_one(Node)
        cmd = CreateSingleArcExample(origin, destination)
        self.assert_arc_creation(cmd, origin, destination)

        cmd = CreateSingleArcExample(origin, destination)
        self.assertRaises(CommandExecutionException, cmd)

    def test_sequential(self):
        class SaveCmd(Command):
            def do_business(self):
                self._to_commit = Node()
                self.result = self._to_commit

        class CreateArcSequentially(CreateArc):
            arc_class = Arc

            def __init__(self):
                super(CreateArcSequentially, self).__init__(destination=Node().put())

            def handle_previous(self, command):
                self.origin = command.result

        save_cmd = SaveCmd()

        create_arc_sequentially = CreateArcSequentially()

        cmd = CommandSequential(save_cmd, create_arc_sequentially)
        cmd()
        self.assert_arc_creation(create_arc_sequentially, save_cmd.result, create_arc_sequentially.destination)

    def assert_arc_creation(self, cmd, origin, destination):
        created_arc = cmd()
        self.assertEqual(to_node_key(origin), to_node_key(cmd.origin))
        self.assertEqual(to_node_key(destination), to_node_key(cmd.destination))
        arc = Arc.query().order(-Arc.creation).get()
        self.assertEqual(arc, created_arc)
        self.assertEqual(to_node_key(origin), to_node_key(arc.origin))
        self.assertEqual(to_node_key(destination), to_node_key(arc.destination))


class HasArcExample(HasArcCommand):
    arc_class = Arc


class HasArcTests(GAETestCase):
    def test_no_arc(self):
        origin = mommy.save_one(Node)
        destination = mommy.save_one(Node)
        self.assertIsNone(HasArcExample(origin=origin)())
        self.assertIsNone(HasArcExample(destination=destination)())
        self.assertIsNone(HasArcExample(origin, destination)())

    def test_has_arc(self):
        origin = mommy.save_one(Node)
        destination = mommy.save_one(Node)
        arc = CreateArcExample(origin, destination)()
        has_arc_cmd = HasArcExample(origin=origin)

        self.assertEqual(arc.key, has_arc_cmd())
        has_arc_cmd = HasArcExample(destination=destination)

        self.assertEqual(arc.key, has_arc_cmd())
        has_arc_cmd = HasArcExample(origin, destination)

        self.assertEqual(arc.key, has_arc_cmd())

    def test_only_origin_has_arc(self):
        origin = mommy.save_one(Node)
        destination = mommy.save_one(Node)
        another_destination = mommy.save_one(Node)
        arc = CreateArcExample(origin, destination)()
        self.assertEqual(arc.key, HasArcExample(origin=origin)())
        self.assertEqual(arc.key, HasArcExample(destination=destination)())
        self.assertEqual(arc.key, HasArcExample(origin, destination)())
        self.assertIsNone(HasArcExample(origin, another_destination)())

    def test_only_destination_has_arc(self):
        origin = mommy.save_one(Node)
        destination = mommy.save_one(Node)
        another_origin = mommy.save_one(Node)
        arc = CreateArcExample(origin, destination)()
        self.assertEqual(arc.key, HasArcExample(origin=origin)())
        self.assertEqual(arc.key, HasArcExample(destination=destination)())
        self.assertEqual(arc.key, HasArcExample(origin, destination)())
        self.assertIsNone(HasArcExample(another_origin, destination)())


class CreateNodeMock(Command):
    def do_business(self):
        self._to_commit = Node()
        self.result = self._to_commit


class CreateUniqueArcExample(CreateUniqueArc):
    arc_class = Arc


class CreateUniqueArcTests(GAETestCase):
    def test_success_with_nodes(self):
        origin = mommy.save_one(Node)
        destination = mommy.save_one(Node)
        CreateUniqueArcExample(origin, destination)()
        has_arc_cmd = HasArcExample(origin, destination)

        self.assertIsNotNone(has_arc_cmd())

    def test_success_with_commands(self):
        origin_cmd = CreateNodeMock()
        destination_cmd = CreateNodeMock()
        CreateUniqueArcExample(origin_cmd, destination_cmd)()
        has_arc_cmd = HasArcExample(origin_cmd.result, destination_cmd.result)

        self.assertIsNotNone(has_arc_cmd())

    def test_has_arc(self):
        origin = mommy.save_one(Node)
        destination = mommy.save_one(Node)
        another_destination_cmd = CreateNodeMock()
        another_origin_cmd = CreateNodeMock()
        CreateArcExample(origin, destination)()
        # Test with nodes
        self.assertRaises(CommandExecutionException, CreateUniqueArcExample(origin, destination).execute)

        # Test with one command
        self.assertRaises(CommandExecutionException, CreateUniqueArcExample(another_origin_cmd, destination))
        self.assertIsNone(another_origin_cmd.result.key, 'Should not save origin once arc could not be created')

        # Test with 2 commands
        self.assertRaises(CommandExecutionException,
                          CreateUniqueArcExample(another_origin_cmd, NodeSearch(destination)))
        self.assertIsNone(another_origin_cmd.result.key, 'Should not save origin once arc could not be created')
        self.assertRaises(CommandExecutionException, CreateUniqueArcExample(origin, another_destination_cmd))
        self.assertIsNone(another_origin_cmd.result.key, 'Should not save destination once arc could not be created')
        self.assertRaises(CommandExecutionException,
                          CreateUniqueArcExample(NodeSearch(origin), another_destination_cmd))
        self.assertIsNone(another_origin_cmd.result.key, 'Should not save destination once arc could not be created')


class CreateSingleOriginArcExample(CreateSingleOriginArc):
    arc_class = Arc


class CreateSingleOriginArcTests(GAETestCase):
    def test_success_with_nodes(self):
        origin = mommy.save_one(Node)
        destination = mommy.save_one(Node)
        CreateSingleOriginArcExample(origin, destination)()
        has_arc_command = HasArcExample(origin, destination)

        self.assertIsNotNone(has_arc_command())

        another_origin = mommy.save_one(Node)
        create_single_origin_cmd = CreateSingleOriginArcExample(another_origin, destination)
        self.assertRaises(CommandExecutionException, create_single_origin_cmd)
        has_arc_command = HasArcExample(another_origin, destination)
        self.assertIsNone(has_arc_command())


class CreateSingleDestinationArcExample(CreateSingleDestinationArc):
    arc_class = Arc


class CreateSingleDestinationArcTests(GAETestCase):
    def test_success_with_nodes(self):
        origin = mommy.save_one(Node)
        destination = mommy.save_one(Node)
        CreateSingleDestinationArcExample(origin, destination)()
        has_arc_cmd = HasArcExample(origin, destination)

        self.assertIsNotNone(has_arc_cmd())

        another_destination = mommy.save_one(Node)
        create_single_destination_cmd = CreateSingleDestinationArcExample(origin, another_destination)
        self.assertRaises(CommandExecutionException, create_single_destination_cmd)
        has_arc_cmd = HasArcExample(origin, another_destination)

        self.assertIsNone(has_arc_cmd())
