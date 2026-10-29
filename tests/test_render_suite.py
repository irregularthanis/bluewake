"""Synthetic checks for the rendered tests (scripts/render_suite.py, render_test and the scripts they run).
No disc, card or app: tests/render_fixtures/fake_bluewake.py writes the frames and log lines instead."""

from pathlib import Path
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import argparse

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / 'scripts'
FAKE = ROOT / 'tests' / 'render_fixtures' / 'fake_bluewake.py'
sys.path.insert(0, str(SCRIPTS))
import bench_rooms
import render_suite
import rendered_run

try:
    import numpy  # noqa: F401
    import PIL  # noqa: F401
    HAVE_IMAGES = True
except ImportError:
    HAVE_IMAGES = False


def write_state(path, retrace):
    """A save state with only its header, as render_suite.state_retrace reads it."""
    with gzip.open(path, 'wb') as out:
        out.write(b'BWSTATE1' + bytes(4) + b'HEADER'.ljust(16, b'\0') + (40).to_bytes(8, 'little')
                  + bytes(32) + retrace.to_bytes(8, 'little'))


class Work(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)

    def app(self, name):
        path = self.dir / 'apps' / name
        path.parent.mkdir(exist_ok=True)
        shutil.copy(FAKE, path)
        path.chmod(0o755)
        return path


class Manifest(unittest.TestCase):
    def test_the_scenes_in_the_repo_are_valid(self):
        scenes = render_suite.scenes_for(SCRIPTS / 'render_scenes.json', 'full')
        self.assertEqual(render_suite.validate(scenes), [])
        quick = render_suite.scenes_for(SCRIPTS / 'render_scenes.json', 'quick')
        self.assertTrue(0 < len(quick) < len(scenes))

    def test_problems_are_named(self):
        problems = render_suite.validate([
            {'name': 'a', 'state': 's', 'length': 10, 'dump': '0:5'},
            {'name': 'a', 'length': '10', 'capture': '1:1', 'colour': 'blue', 'pad': '1885:B:6'},
            {'name': 'b', 'state': 's', 'length': 10}], {'s': {'warp': 'Outset'}})
        text = '\n'.join(problems)
        for expected in ('dump needs smooth', 'name used twice', 'no state', 'length (retraces after the state)',
                         'unknown keys colour', 'b: give capture or dump', "pad press '1885:B:6'",
                         'state s: give tour: true, or warp'):
            self.assertIn(expected, text)


class Rooms(unittest.TestCase):
    def rows(self, a, b, arrived='True'):
        return [{'room': 'sea:43:0', 'name': 'Sector 2B', 'variant': v, 'arrived': arrived, 'gpu_ms': str(x),
                 'busy': '60'} for v, xs in (('A', a), ('B', b)) for x in xs]

    def test_within_noise_is_not_flagged(self):
        [room] = render_suite.compare_rooms(self.rows([4.0, 4.6, 4.1], [4.2, 4.0, 4.5]), 5.0)
        self.assertEqual(room['flags'], [])

    def test_a_real_slowdown_is_flagged(self):
        [room] = render_suite.compare_rooms(self.rows([6.0, 6.1, 6.05], [4.0, 4.05, 4.1]), 5.0)
        self.assertEqual(room['flags'], ['gpu_ms +49.4%'])

    def test_a_small_steady_change_under_the_floor_is_not_flagged(self):
        [room] = render_suite.compare_rooms(self.rows([4.1, 4.1], [4.0, 4.0]), 5.0)
        self.assertEqual(room['flags'], [])

    def test_a_room_not_reached_is_flagged(self):
        [room] = render_suite.compare_rooms(self.rows([4.0], [4.0], arrived='False'), 5.0)
        self.assertIn('did not arrive', room['flags'])

    def test_bench_rooms_reads_the_sweep_picks(self):
        rooms = bench_rooms.read_rooms(SCRIPTS / 'bench_rooms.tsv')
        self.assertEqual(rooms[0], ('38.4', 'SubD51:1:0', 'SubD51'))
        self.assertEqual(len(rooms), 20)


class Report(unittest.TestCase):
    summary = {'host': 'steamdeck', 'gpu': 'AMD Custom GPU 0405', 'display': 'headless 1280x800',
               'suite': 'quick', 'repeat': 3, 'a': 'new', 'b': 'main',
               'scenes': [{'name': 'outset-trees-swing', 'verdict': 'identical', 'images': 160, 'max_diff': 0,
                           'min_psnr': None, 'flicker_a': 0, 'flicker_b': 0, 'why': ''}],
               'rooms': [{'room': 'SubD51:1:0', 'name': 'SubD51', 'flags': [],
                          'gpu_ms': {'a': 9.1, 'b': 9.2, 'delta_pct': -1.1, 'spread': 0.3},
                          'busy': {'a': 71.0, 'b': 72.0, 'delta_pct': -1.4, 'spread': 2.0}}]}

    def test_terminal_and_github(self):
        text = render_suite.report(self.summary, 'terminal')
        self.assertIn('outset-trees-swing', text)
        self.assertTrue(text.rstrip().endswith('PASS'))
        github = render_suite.report(self.summary, 'github')
        self.assertIn('| SubD51:1:0 | SubD51 | 9.1 | 9.2 | 71 | 72 | -1.1% | ok |', github)
        self.assertEqual(render_suite.status(self.summary), 0)

    def test_a_changed_scene_fails(self):
        summary = json.loads(json.dumps(self.summary))
        summary['scenes'][0]['verdict'] = 'changed'
        self.assertEqual(render_suite.status(summary), 1)
        self.assertTrue(render_suite.report(summary, 'terminal').rstrip().endswith('FAIL'))


class Timeout(Work):
    def test_a_hung_run_is_stopped_and_marked(self):
        result = rendered_run.run(self.app('hang'), FAKE, self.dir / 'run', {}, self.dir / 'status.txt', 0,
                                  timeout=1)
        self.assertTrue(result['timed_out'])

    def test_an_empty_quest_log_ends_the_run_at_once(self):
        result = rendered_run.run(self.app('empty'), FAKE, self.dir / 'run', {}, self.dir / 'status.txt', 0,
                                  timeout=60, stop_on='is empty; stopped pressing A')
        self.assertFalse(result['timed_out'])
        self.assertLess(result['seconds'], 15)


@unittest.skipUnless(HAVE_IMAGES, 'needs numpy and Pillow')
class Check(Work):
    def frames(self, name, dump=False):
        env = dict(os.environ)
        out = self.dir / name
        out.mkdir()
        if dump:
            env.update(DOL_AURORA_FRAME_INTERP_DUMP=str(out), DOL_AURORA_FRAME_INTERP_DUMP_FROM='0',
                       DOL_AURORA_FRAME_INTERP_DUMP_TO='8')
        else:
            env.update(BLUEWAKE_CAPTURE_OPENING_FRAME=str(out / 'frame.ppm'), BLUEWAKE_CAPTURE_RETRACE='100',
                       BLUEWAKE_CAPTURE_INTERVAL='30', BLUEWAKE_MAX_RETRACES='280')
        subprocess.run([str(self.app(name))], env=env, stdout=subprocess.DEVNULL, check=True)
        return out

    def check(self, a, b, *extra):
        out = self.dir / f'{a.name}-{b.name}.json'
        subprocess.run([sys.executable, str(SCRIPTS / 'frame_compare.py'), 'check', str(a), str(b), '--json',
                        str(out), *extra], stdout=subprocess.DEVNULL)
        return json.loads(out.read_text())

    def test_verdicts(self):
        plain, again = self.frames('plain'), self.frames('plain-again')
        self.assertEqual(self.check(plain, again)['verdict'], 'identical')
        self.assertEqual(self.check(self.frames('noise'), plain)['verdict'], 'similar')
        self.assertEqual(self.check(self.frames('bright'), plain)['verdict'], 'changed')
        empty = self.dir / 'empty'
        empty.mkdir()
        self.assertEqual(self.check(empty, plain)['verdict'], 'failed')

    def test_new_flicker_fails(self):
        result = self.check(self.frames('flicker', dump=True), self.frames('plain', dump=True),
                            '--flicker-margin', '10')
        self.assertEqual(result['verdict'], 'failed')
        self.assertIn('new flicker', result['why'])
        self.assertGreater(result['flicker_a'], result['flicker_b'])


@unittest.skipUnless(HAVE_IMAGES, 'needs numpy and Pillow')
class EndToEnd(Work):
    def suite(self, a, b, *extra):
        (self.dir / 'states').mkdir(exist_ok=True)
        write_state(self.dir / 'states' / 'tour.bwstate', 2390)
        (self.dir / 'card').write_bytes(b'card')
        out = self.dir / f'out-{a}-{b}'
        code = subprocess.run([sys.executable, str(SCRIPTS / 'render_suite.py'), 'run', str(self.app(a)),
                               str(self.app(b)), str(out), '--card', str(self.dir / 'card'), '--states',
                               str(self.dir / 'states'), '--repeat', '2', '--display', 'desktop', *extra],
                              stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT).returncode
        return code, json.loads((out / 'summary.json').read_text())

    def test_the_same_build_passes(self):
        code, summary = self.suite('plain', 'plain-b')
        self.assertEqual(code, 0, summary)
        self.assertEqual({s['verdict'] for s in summary['scenes']}, {'identical'})
        self.assertEqual(len(summary['rooms']), 3)

    def test_a_different_picture_and_a_slower_gpu_fail(self):
        code, summary = self.suite('bright-slow', 'plain')
        self.assertEqual(code, 1)
        self.assertEqual({s['verdict'] for s in summary['scenes']}, {'changed'})
        self.assertTrue(all(any(f.startswith('gpu_ms +') for f in r['flags']) for r in summary['rooms']))

    def test_collect_needs_no_frames_back_when_a_and_b_match(self):
        (self.dir / 'states').mkdir()
        write_state(self.dir / 'states' / 'tour.bwstate', 2390)
        (self.dir / 'card').write_bytes(b'card')
        suite = [sys.executable, str(SCRIPTS / 'render_suite.py')]
        for a, b in (('plain', 'plain-b'), ('bright', 'plain')):
            out = self.dir / f'{a}-{b}'
            subprocess.run(suite + ['collect', str(self.app(a)), str(self.app(b)), str(out), '--card',
                                    str(self.dir / 'card'), '--states', str(self.dir / 'states'), '--repeat', '1',
                                    '--display', 'desktop'], stdout=subprocess.DEVNULL, check=True)
            differing = subprocess.run(suite + ['differing', str(out)], capture_output=True, text=True).stdout.split()
            for frame in out.glob('scenes/**/*.ppm'):  # what render_test leaves on the target
                frame.unlink()
            code = subprocess.run(suite + ['analyze', str(out)], stdout=subprocess.DEVNULL).returncode
            summary = json.loads((out / 'summary.json').read_text())
            if a == 'plain':
                self.assertEqual(differing, [])
                self.assertEqual(code, 0)
                self.assertEqual({s['verdict'] for s in summary['scenes']}, {'identical'})
            else:
                self.assertEqual(differing, ['tour-1-outset', 'tour-2-windfall', 'tour-3-dragon-roost-cavern',
                                             'tour-4-forest-haven', 'tour-5-sea-by-the-fortress', 'outset-swing'])
                self.assertEqual({s['why'] for s in summary['scenes']}, {'frames differ but were not copied here'})

    def test_the_tour_state_is_made_and_kept_with_its_card(self):
        (self.dir / 'states').mkdir()
        (self.dir / 'states' / 'tour.bwstate').write_bytes(b's\n')  # a placeholder: the game hangs on it
        (self.dir / 'card').write_bytes(b'card')
        args = argparse.Namespace(card=str(self.dir / 'card'), states=str(self.dir / 'states'))
        copy = lambda source, dest: [sys.executable, '-c', 'import shutil, sys; shutil.copy(*sys.argv[1:])',
                                     str(source), str(dest)]  # card_set_restart.py needs a real card
        with mock.patch('bench_tour.card_restart_argv', copy):
            failed = render_suite.make_tour_state('tour.bwstate', self.app('plain'), self.dir / 'out', args,
                                                  dict(os.environ))
        self.assertIsNone(failed)
        self.assertEqual(render_suite.state_retrace(self.dir / 'states' / 'tour.bwstate'), 2390)
        self.assertEqual((self.dir / 'states' / 'tour.card').read_bytes(), b'card')

    def test_the_tour_is_one_scene_a_stop(self):
        code, summary = self.suite('plain', 'plain-b')
        tour = [s for s in summary['scenes'] if s.get('scene') == 'tour']
        self.assertEqual([s['name'] for s in tour], ['tour-1-outset', 'tour-2-windfall',
                                                     'tour-3-dragon-roost-cavern', 'tour-4-forest-haven',
                                                     'tour-5-sea-by-the-fortress'])
        self.assertEqual({s['images'] for s in tour}, {5})

    def test_a_state_without_a_recipe_stops_before_running(self):
        (self.dir / 'states').mkdir()
        (self.dir / 'card').write_bytes(b'card')
        scenes = self.dir / 'scenes.json'
        scenes.write_text(json.dumps({'scenes': [{'name': 'x', 'state': 'mine.bwstate', 'length': 60,
                                                  'capture': '0:30'}]}))
        code = subprocess.run([sys.executable, str(SCRIPTS / 'render_suite.py'), 'collect', str(self.app('plain')),
                               str(self.app('plain-b')), str(self.dir / 'out'), '--card', str(self.dir / 'card'),
                               '--states', str(self.dir / 'states'), '--scenes', str(scenes), '--display', 'desktop'],
                              capture_output=True, text=True)
        self.assertEqual(code.returncode, 2)
        self.assertIn('no recipe to make it', code.stderr)


class Timing(unittest.TestCase):
    def test_scene_retraces_count_from_the_state(self):
        scene = {'length': 180, 'pad': '30:0x0200:6,60:0x0200:6:0:80', 'capture': '30:30'}
        self.assertEqual(render_suite.shifted(scene, 1000),
                         {'max_retraces': 1180, 'pad': '1030:0x0200:6,1060:0x0200:6:0:80', 'capture': '1030:30'})

    def test_a_file_that_is_not_a_state_has_no_retrace(self):
        with tempfile.NamedTemporaryFile() as f:
            f.write(b's\n')
            f.flush()
            self.assertIsNone(render_suite.state_retrace(f.name))


class Wrapper(unittest.TestCase):
    def test_help_and_bad_arguments(self):
        script = SCRIPTS / 'render_test'
        self.assertEqual(subprocess.run(['bash', str(script), '--help'], capture_output=True).returncode, 0)
        bad = subprocess.run(['bash', str(script), 'a', 'b', '--suite', 'huge'], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)


if __name__ == '__main__':
    unittest.main()
