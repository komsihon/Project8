# -*- coding: utf-8 -*-
import os

__author__ = 'Kom Sihon'


CNMX_EXTENSION = 'cnmx'
PREFIXES = ['cine', 'da', 'clip', 'tuto', 'Hd', 'comedie', 'oms', 'gag', 'xxl', 'doc', 'Xcamer']


def get_path_info(filename):
    naked_filename = get_filename(filename)
    rev_enc_naked_filename = '%s.%s' % (naked_filename[::-1], CNMX_EXTENSION)  # Reversed encrypted naked filename
    folder = filename.replace(naked_filename, '')
    rev_folder = reverse_folder(folder)
    return {
        'rev_rel_folder': rev_folder,  # Reversed relative folder in the source location
        'rev_naked_filename': strip_extension(rev_enc_naked_filename),
        'rev_enc_naked_filename': rev_enc_naked_filename
    }


def reverse_folder(path, sep=None):
    """
    Reverse the path of a folder:
    reverse_folder('Prison.Break/Season1/') = 'kaerB.nosirP/1nosaeS/'
    """
    if path == '':
        return ''
    if sep is None:
        sep = os.sep
    tokens = path.split(sep)
    reversed_folder = ''
    for token in tokens:
        reversed_folder += '%s%s' % (os.sep, token[::-1])
    return reversed_folder[1:]


def reverse_path(path, sep=None):
    """
    Reverse the whole path of a file:
    reverse_folder('Prison.Break/Season1/S01E02.avi') = 'kaerB.nosirP/1nosaeS/iva.20E10S'
    """
    filename = get_filename(path)
    folder = path.replace(filename, '')
    return '%s%s' % (reverse_folder(folder, sep), filename[::-1])


def unpack_files(files):
    """
    Some files from order may be in the form of multiple elements separated by a comma, this function
    takes a list of movies from an order and transforms it into another list of single files elements
    Eg: An original list like this
    L1 = [
        'A.avi',
        'B1.avi, B2.avi',
        'C.avi',
        'D1.avi, D2.avi, D3.avi'
    ]
    will generate elements in the form
    L2 = ['A.avi', 'B1.avi', 'B2.avi', 'C.avi', 'D1.avi', 'D2.avi', 'D3.avi']
    """
    for filename in files:
        pack = filename.split(',')
        for name in pack:
            yield name.strip()


def get_base_folder(file_path):
    """
    Gets the base folder of a file path
    get_base_folder('Heroes/Season1/episode1.avi') = 'Heroes'
    """
    idx = file_path.find(os.sep)
    base_folder = file_path[:idx]
    return base_folder if base_folder else '/'


def get_folders(file_path):
    """
    Gets the subsquent folders in a file path
    get_folders('/home/root/Documents/somefile.avi') = '/home/root/Documents/'
    """
    idx = file_path.rfind(os.sep) + 1
    return file_path[:idx]


def get_filename(file_path):
    """
    Gets the filename only part of a file path
    get_filename('/home/root/Documents/somefile.avi') = 'somefile.avi'
    """
    idx = file_path.rfind(os.sep) + 1
    return file_path[idx:]


def strip_prefix(filename):
    """
    Strips the common prefixes from the original filename in source; those are often cine_, da_, xxl_
    strip_prefix('cine_somefile.avi') = 'somefile.avi'
    """
    for prefix in PREFIXES:
        if prefix[-1] != '_':
            prefix += '_'
        filename = filename.replace(prefix, '')
    return filename


def get_extension(filename):
    """
    Finds and returns the extension of a filename
    :param filename:
    :return:
    """
    idx = filename.rfind('.') + 1
    return filename[idx:]


def strip_extension(filename):
    """
    Strips the extension from the original filename in source; those are often .avi, .mkv, etc
    strip_extension('somefile.avi') = 'somefile'
    """
    idx = filename.rfind('.')
    return filename[:idx]


def encrypt_filename(filename):
    """
    'Encrypts' the whole path of a file:
    reverse_folder('Prison.Break/Season1/S01E02.avi') = 'kaerB.nosirP/1nosaeS/iva.20E10S.cnmx'
    """
    return reverse_path(filename) + '.' + CNMX_EXTENSION


def decrypt_filename(filename):
    """
    'Decrypts' the whole path of a file:
    reverse_folder('kaerB.nosirP/1nosaeS/iva.20E10S.cnmx') = 'Prison.Break/Season1/S01E02.avi'
    """
    filename = filename.replace('.' + CNMX_EXTENSION, '')
    return reverse_path(filename)


def calculate_free_space(mount_point):
    """
    Calculates the amount of free space on the given mount_point
    """
    if os.name == 'posix':
        v = os.statvfs(mount_point)
        free_space = v.f_frsize * v.f_bfree
        return free_space
    else:
        import ctypes
        from ctypes import windll
        free_bytes = ctypes.c_int64()
        total_bytes = ctypes.c_int64()
        windll.kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar_p(mount_point), ctypes.byref(free_bytes), ctypes.byref(total_bytes), None)
        return free_bytes.value