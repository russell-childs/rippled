# Copyright 2014 Vinnie Falco (vinnie.falco@gmail.com)
# Portions Copyright The SCons Foundation
# This file is part of beast

"""
A SCons tool to provide a family of scons builders that
generate Visual Studio project files
"""

import collections
import hashlib
import itertools
import ntpath
import os
import random
import re

import SCons.Builder
import SCons.Node.FS
import SCons.Util


import sys

#-------------------------------------------------------------------------------

# Adapted from msvs.py

V12DSPHeader = """\
<?xml version="1.0" encoding="%(encoding)s"?>
<Project DefaultTargets="Build" ToolsVersion="12.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
"""

V12DSPProjectConfiguration = """\
\t\t<ProjectConfiguration Include="%(variant)s|%(platform)s">
\t\t\t<Configuration>%(variant)s</Configuration>
\t\t\t<Platform>%(platform)s</Platform>
\t\t</ProjectConfiguration>
"""

V12DSPGlobals = """\
\t<PropertyGroup Label="Globals">
\t\t<ProjectGuid>%(project_guid)s</ProjectGuid>
\t\t<Keyword>Win32Proj</Keyword>
\t\t<RootNamespace>%(name)s</RootNamespace>
\t\t<IgnoreWarnCompileDuplicatedFilename>true</IgnoreWarnCompileDuplicatedFilename>
\t</PropertyGroup>
"""

V12DSPPropertyGroup = """\
\t<PropertyGroup Condition="'$(Configuration)|$(Platform)'=='%(variant)s|%(platform)s'" Label="Configuration">
\t\t<CharacterSet>MultiByte</CharacterSet>
\t\t<ConfigurationType>Application</ConfigurationType>
\t\t<PlatformToolset>v120</PlatformToolset>
\t\t<LinkIncremental>False</LinkIncremental>
\t\t<UseDebugLibraries>%(use_debug_libs)s</UseDebugLibraries>
\t\t<UseOfMfc>False</UseOfMfc>
\t\t<WholeProgramOptimization>false</WholeProgramOptimization>
\t</PropertyGroup>
"""

V12DSPImportGroup= """\
\t<ImportGroup Condition="'$(Configuration)|$(Platform)'=='%(variant)s|%(platform)s'" Label="PropertySheets">
\t\t<Import Project="$(UserRootDir)\Microsoft.Cpp.$(Platform).user.props" Condition="exists('$(UserRootDir)\Microsoft.Cpp.$(Platform).user.props')" Label="LocalAppDataPlatform" />
\t</ImportGroup>
"""

V12DSPItemDefinitionGroup= """\
\t<ItemDefinitionGroup Condition="'$(Configuration)|$(Platform)'=='%(variant)s|%(platform)s'">
"""

_xml_filters_header = (
'''<?xml version="1.0" encoding="utf-8"?>
<Project ToolsVersion="4.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
\t<ItemGroup>
''')

#-------------------------------------------------------------------------------

def itemList(items, sep):
    if type(items) == str:  # Won't work in Python 3.
        return items
    def gen():
        for item in sorted(items):
            if type(item) == dict:
                for k, v in item.items():
                    yield k + '=' + v
            else:
                yield item
            yield sep
    return ''.join(gen())

#-------------------------------------------------------------------------------

class SwitchConverter(object):
    '''Converts command line switches to MSBuild XML, using tables'''

    def __init__(self, table, booltable):
        self.table = {}
        for key in table:
            self.table[key] = table[key]
        for key in booltable:
            value = booltable[key]
            self.table[key] = [value[0], 'True']
            self.table[key + '-'] = [value[0], 'False']

    def getXml(self, switches):
        if type(switches) != list:
            switches = list(switches)
        xml = []
        unknown = []
        for switch in switches:
            try:
                value = self.table[switch]
                xml.append (
                    '<%s>%s</%s>' % (value[0], value[1], value[0]))
            except:
                unknown.append(switch)
        xml.append (
            '<AdditionalOptions>%s%%(AdditionalOptions)</AdditionalOptions>' % (
                itemList(unknown, ' ')))
        return xml

class ClSwitchConverter(SwitchConverter):
    def __init__(self):
        booltable = {
            '/C'            : ['KeepComments'],
            '/doc'          : ['GenerateXMLDocumentationFiles'],
            '/FAu'          : ['UseUnicodeForAssemblerListing'],
            '/FC'           : ['UseFullPaths'],
            '/FR'           : ['BrowseInformation'],
            '/Fr'           : ['BrowseInformation'],
            '/Fx'           : ['ExpandAttributedSource'],
            '/GF'           : ['StringPooling'],
            '/GL'           : ['WholeProgramOptimization'],
            '/Gm'           : ['MinimalRebuild'],
            '/GR'           : ['RuntimeTypeInfo'],
            '/GS'           : ['BufferSecurityCheck'],
            '/GT'           : ['EnableFiberSafeOptimizations'],
            '/Gy'           : ['FunctionLevelLinking'],
            '/MP'           : ['MultiProcessorCompilation'],
            '/Oi'           : ['IntrinsicFunctions'],
            '/Oy'           : ['OmitFramePointers'],
            '/RTCc'         : ['SmallerTypeCheck'],
            '/u'            : ['UndefineAllPreprocessorDefinitions'],
            '/X'            : ['IgnoreStandardIncludePath'],
            '/WX'           : ['TreatWarningAsError'],
            '/Za'           : ['DisableLanguageExtensions'],
            '/Zl'           : ['OmitDefaultLibName'],
            '/fp:except'    : ['FloatingPointExceptions'],
            '/hotpatch'     : ['CreateHotpatchableImage'],
            '/nologo'       : ['SuppressStartupBanner'],
            '/openmp'       : ['OpenMPSupport'],
            '/showIncludes' : ['ShowIncludes'],
            '/Zc:forScope'  : ['ForceConformanceInForLoopScope'],
            '/Zc:wchar_t'   : ['TreatWChar_tAsBuiltInType'],
        }
        table = {
            '/EHsc' : ['ExceptionHandling', 'Sync'],
            '/EHa'  : ['ExceptionHandling', 'Async'],
            '/EHs'  : ['ExceptionHandling', 'SyncCThrow'],
            '/FA'   : ['AssemblerOutput', 'AssemblyCode'],
            '/FAcs' : ['AssemblerOutput', 'All'],
            '/FAc'  : ['AssemblerOutput', 'AssemblyAndMachineCode'],
            '/FAs'  : ['AssemblerOutput', 'AssemblyAndSourceCode'],
            '/Gd'   : ['CallingConvention', 'Cdecl'],
            '/Gr'   : ['CallingConvention', 'FastCall'],
            '/Gz'   : ['CallingConvention', 'StdCall'],
            '/MT'   : ['RuntimeLibrary', 'MultiThreaded'],
            '/MTd'  : ['RuntimeLibrary', 'MultiThreadedDebug'],
            '/MD'   : ['RuntimeLibrary', 'MultiThreadedDLL'],
            '/MDd'  : ['RuntimeLibrary', 'MultiThreadedDebugDLL'],
            '/Od'   : ['Optimization', 'Disabled'],
            '/O1'   : ['Optimization', 'MinSpace'],
            '/O2'   : ['Optimization', 'MaxSpeed'],
            '/Ox'   : ['Optimization', 'Full'],
            '/Ob1'  : ['InlineFunctionExpansion', 'OnlyExplicitInline'],
            '/Ob2'  : ['InlineFunctionExpansion', 'AnySuitable'],
            '/Ot'   : ['FavorSizeOrSpeed', 'Speed'],
            '/Os'   : ['FavorSizeOrSpeed', 'Size'],
            '/RTCs' : ['BasicRuntimeChecks', 'StackFrameRuntimeCheck'],
            '/RTCu' : ['BasicRuntimeChecks', 'UninitializedLocalUsageCheck'],
            '/RTC1' : ['BasicRuntimeChecks', 'EnableFastChecks'],
            '/TC'   : ['CompileAs', 'CompileAsC'],
            '/TP'   : ['CompileAs', 'CompileAsCpp'],
            '/W0'   : [ 'WarningLevel', 'TurnOffAllWarnings'],
            '/W1'   : [ 'WarningLevel', 'Level1'],
            '/W2'   : [ 'WarningLevel', 'Level2'],
            '/W3'   : [ 'WarningLevel', 'Level3'],
            '/W4'   : [ 'WarningLevel', 'Level4'],
            '/Wall' : [ 'WarningLevel', 'EnableAllWarnings'],
            '/Yc'   : ['PrecompiledHeader', 'Create'],
            '/Yu'   : ['PrecompiledHeader', 'Use'],
            '/Z7'   : ['DebugInformationFormat', 'OldStyle'],
            '/Zi'   : ['DebugInformationFormat', 'ProgramDatabase'],
            '/ZI'   : ['DebugInformationFormat', 'EditAndContinue'],
            '/Zp1'  : ['StructMemberAlignment', '1Byte'],
            '/Zp2'  : ['StructMemberAlignment', '2Bytes'],
            '/Zp4'  : ['StructMemberAlignment', '4Bytes'],
            '/Zp8'  : ['StructMemberAlignment', '8Bytes'],
            '/Zp16'         : ['StructMemberAlignment', '16Bytes'],
            '/arch:IA32'     : ['EnableEnhancedInstructionSet', 'NoExtensions'],
            '/arch:SSE'      : ['EnableEnhancedInstructionSet', 'StreamingSIMDExtensions'],
            '/arch:SSE2'     : ['EnableEnhancedInstructionSet', 'StreamingSIMDExtensions2'],
            '/arch:AVX'      : ['EnableEnhancedInstructionSet', 'AdvancedVectorExtensions'],
            '/clr'           : ['CompileAsManaged', 'True'],
            '/clr:pure'      : ['CompileAsManaged', 'Pure'],
            '/clr:safe'      : ['CompileAsManaged', 'Safe'],
            '/clr:oldSyntax' : ['CompileAsManaged', 'OldSyntax'],
            '/fp:fast'       : ['FloatingPointModel', 'Fast'],
            '/fp:precise'    : ['FloatingPointModel', 'Precise'],
            '/fp:strict'     : ['FloatingPointModel', 'Strict'],
            '/errorReport:none'   : ['ErrorReporting', 'None'],
            '/errorReport:prompt' : ['ErrorReporting', 'Prompt'],
            '/errorReport:queue'  : ['ErrorReporting', 'Queue'],
            '/errorReport:send'   : ['ErrorReporting', 'Send'],
        }
        # Ideas from Google's Generate Your Project
        '''
        _Same(_compile, 'AdditionalIncludeDirectories', _folder_list)  # /I

        _Same(_compile, 'PreprocessorDefinitions', _string_list)  # /D
        _Same(_compile, 'DisableSpecificWarnings', _string_list)  # /wd
        _Same(_compile, 'ProgramDataBaseFileName', _file_name)  # /Fd

        _Same(_compile, 'AdditionalOptions', _string_list)
        _Same(_compile, 'AdditionalUsingDirectories', _folder_list)  # /AI
        _Same(_compile, 'AssemblerListingLocation', _file_name)  # /Fa
        _Same(_compile, 'BrowseInformationFile', _file_name)
        _Same(_compile, 'ForcedIncludeFiles', _file_list)  # /FI
        _Same(_compile, 'ForcedUsingFiles', _file_list)  # /FU
        _Same(_compile, 'UndefinePreprocessorDefinitions', _string_list)  # /U
        _Same(_compile, 'XMLDocumentationFileName', _file_name)
           ''    : ['EnablePREfast', _boolean)  # /analyze Visible='false'
        _Renamed(_compile, 'ObjectFile', 'ObjectFileName', _file_name)  # /Fo
        _Renamed(_compile, 'PrecompiledHeaderThrough', 'PrecompiledHeaderFile',
                 _file_name)  # Used with /Yc and /Yu
        _Renamed(_compile, 'PrecompiledHeaderFile', 'PrecompiledHeaderOutputFile',
                 _file_name)  # /Fp
        _ConvertedToAdditionalOption(_compile, 'DefaultCharIsUnsigned', '/J')
        _MSBuildOnly(_compile, 'ProcessorNumber', _integer)  # the number of processors
        _MSBuildOnly(_compile, 'TrackerLogDirectory', _folder_name)
        _MSBuildOnly(_compile, 'TreatSpecificWarningsAsErrors', _string_list)  # /we
        _MSBuildOnly(_compile, 'PreprocessOutputPath', _string)  # /Fi
        '''
        SwitchConverter.__init__(self, table, booltable)

class LinkSwitchConverter(SwitchConverter):
    def __init__(self):
        # Based on code in Generate Your Project
        booltable = {
            '/DEBUG'                : ['GenerateDebugInformation'],
            '/DYNAMICBASE'          : ['RandomizedBaseAddress'],
            '/DYNAMICBASE'          : ['RandomizedBaseAddress'],
            '/DYNAMICBASE'          : ['RandomizedBaseAddress'],
            '/DYNAMICBASE'          : ['RandomizedBaseAddress'],
            '/DYNAMICBASE'          : ['RandomizedBaseAddress'],
            '/NOLOGO'               : ['SuppressStartupBanner'],
            '/nologo'               : ['SuppressStartupBanner'],
        }
        table = {
            '/ERRORREPORT:NONE'     : ['ErrorReporting', 'NoErrorReport'],
            '/ERRORREPORT:PROMPT'   : ['ErrorReporting', 'PromptImmediately'],
            '/ERRORREPORT:QUEUE'    : ['ErrorReporting', 'QueueForNextLogin'],
            '/ERRORREPORT:SEND'     : ['ErrorReporting', 'SendErrorReport'],
            '/MACHINE:X86'          : ['TargetMachine', 'MachineX86'],
            '/MACHINE:ARM'          : ['TargetMachine', 'MachineARM'],
            '/MACHINE:EBC'          : ['TargetMachine', 'MachineEBC'],
            '/MACHINE:IA64'         : ['TargetMachine', 'MachineIA64'],
            '/MACHINE:MIPS'         : ['TargetMachine', 'MachineMIPS'],
            '/MACHINE:MIPS16'       : ['TargetMachine', 'MachineMIPS16'],
            '/MACHINE:MIPSFPU'      : ['TargetMachine', 'MachineMIPSFPU'],
            '/MACHINE:MIPSFPU16'    : ['TargetMachine', 'MachineMIPSFPU16'],
            '/MACHINE:SH4'          : ['TargetMachine', 'MachineSH4'],
            '/MACHINE:THUMB'        : ['TargetMachine', 'MachineTHUMB'],
            '/MACHINE:X64'          : ['TargetMachine', 'MachineX64'],
            '/NXCOMPAT'             : ['DataExecutionPrevention', 'true'],
            '/NXCOMPAT:NO'          : ['DataExecutionPrevention', 'false'],
            '/SUBSYSTEM:CONSOLE'                    : ['SubSystem', 'Console'],
            '/SUBSYSTEM:WINDOWS'                    : ['SubSystem', 'Windows'],
            '/SUBSYSTEM:NATIVE'                     : ['SubSystem', 'Native'],
            '/SUBSYSTEM:EFI_APPLICATION'            : ['SubSystem', 'EFI Application'],
            '/SUBSYSTEM:EFI_BOOT_SERVICE_DRIVER'    : ['SubSystem', 'EFI Boot Service Driver'],
            '/SUBSYSTEM:EFI_ROM'                    : ['SubSystem', 'EFI ROM'],
            '/SUBSYSTEM:EFI_RUNTIME_DRIVER'         : ['SubSystem', 'EFI Runtime'],
            '/SUBSYSTEM:WINDOWSCE'                  : ['SubSystem', 'WindowsCE'],
            '/SUBSYSTEM:POSIX'                      : ['SubSystem', 'POSIX'],
        }
        '''
        /TLBID:1 /MANIFEST /MANIFESTUAC:level='asInvoker' uiAccess='false'

        _Same(_link, 'AllowIsolation', _boolean)  # /ALLOWISOLATION
        _Same(_link, 'CLRUnmanagedCodeCheck', _boolean)  # /CLRUNMANAGEDCODECHECK
        _Same(_link, 'DelaySign', _boolean)  # /DELAYSIGN
        _Same(_link, 'EnableUAC', _boolean)  # /MANIFESTUAC
        _Same(_link, 'GenerateMapFile', _boolean)  # /MAP
        _Same(_link, 'IgnoreAllDefaultLibraries', _boolean)  # /NODEFAULTLIB
        _Same(_link, 'IgnoreEmbeddedIDL', _boolean)  # /IGNOREIDL
        _Same(_link, 'MapExports', _boolean)  # /MAPINFO:EXPORTS
        _Same(_link, 'StripPrivateSymbols', _file_name)  # /PDBSTRIPPED
        _Same(_link, 'PerUserRedirection', _boolean)
        _Same(_link, 'Profile', _boolean)  # /PROFILE
        _Same(_link, 'RegisterOutput', _boolean)
        _Same(_link, 'SetChecksum', _boolean)  # /RELEASE
        _Same(_link, 'SupportUnloadOfDelayLoadedDLL', _boolean)  # /DELAY:UNLOAD
        
        _Same(_link, 'SwapRunFromCD', _boolean)  # /SWAPRUN:CD
        _Same(_link, 'TurnOffAssemblyGeneration', _boolean)  # /NOASSEMBLY
        _Same(_link, 'UACUIAccess', _boolean)  # /uiAccess='true'
        _Same(_link, 'EnableCOMDATFolding', _newly_boolean)  # /OPT:ICF
        _Same(_link, 'FixedBaseAddress', _newly_boolean)  # /FIXED
        _Same(_link, 'LargeAddressAware', _newly_boolean)  # /LARGEADDRESSAWARE
        _Same(_link, 'OptimizeReferences', _newly_boolean)  # /OPT:REF
        _Same(_link, 'TerminalServerAware', _newly_boolean)  # /TSAWARE

        _Same(_link, 'AdditionalDependencies', _file_list)
        _Same(_link, 'AdditionalLibraryDirectories', _folder_list)  # /LIBPATH 
        _Same(_link, 'AdditionalManifestDependencies', _file_list)  # /MANIFESTDEPENDENCY:
        _Same(_link, 'AdditionalOptions', _string_list)
        _Same(_link, 'AddModuleNamesToAssembly', _file_list)  # /ASSEMBLYMODULE
        _Same(_link, 'AssemblyLinkResource', _file_list)  # /ASSEMBLYLINKRESOURCE
        _Same(_link, 'BaseAddress', _string)  # /BASE
        _Same(_link, 'DelayLoadDLLs', _file_list)  # /DELAYLOAD
        _Same(_link, 'EmbedManagedResourceFile', _file_list)  # /ASSEMBLYRESOURCE
        _Same(_link, 'EntryPointSymbol', _string)  # /ENTRY
        _Same(_link, 'ForceSymbolReferences', _file_list)  # /INCLUDE
        _Same(_link, 'FunctionOrder', _file_name)  # /ORDER
        _Same(_link, 'HeapCommitSize', _string)
        _Same(_link, 'HeapReserveSize', _string)  # /HEAP
        _Same(_link, 'ImportLibrary', _file_name)  # /IMPLIB
        _Same(_link, 'KeyContainer', _file_name)  # /KEYCONTAINER
        _Same(_link, 'KeyFile', _file_name)  # /KEYFILE
        _Same(_link, 'ManifestFile', _file_name)  # /ManifestFile
        _Same(_link, 'MapFileName', _file_name)
        _Same(_link, 'MergedIDLBaseFileName', _file_name)  # /IDLOUT
        _Same(_link, 'MergeSections', _string)  # /MERGE
        _Same(_link, 'MidlCommandFile', _file_name)  # /MIDL
        _Same(_link, 'ModuleDefinitionFile', _file_name)  # /DEF
        _Same(_link, 'OutputFile', _file_name)  # /OUT
        _Same(_link, 'ProfileGuidedDatabase', _file_name)  # /PGD
        _Same(_link, 'ProgramDatabaseFile', _file_name)  # /PDB
        _Same(_link, 'StackCommitSize', _string)
        _Same(_link, 'StackReserveSize', _string)  # /STACK
        _Same(_link, 'TypeLibraryFile', _file_name)  # /TLBOUT
        _Same(_link, 'TypeLibraryResourceID', _integer)  # /TLBID
        _Same(_link, 'Version', _string)  # /VERSION


        _Same(_link, 'AssemblyDebug',
              _Enumeration(['',
                            'true',  # /ASSEMBLYDEBUG
                            'false']))  # /ASSEMBLYDEBUG:DISABLE
        _Same(_link, 'CLRImageType',
              _Enumeration(['Default',
                            'ForceIJWImage',  # /CLRIMAGETYPE:IJW
                            'ForcePureILImage',  # /Switch="CLRIMAGETYPE:PURE
                            'ForceSafeILImage']))  # /Switch="CLRIMAGETYPE:SAFE
        _Same(_link, 'CLRThreadAttribute',
              _Enumeration(['DefaultThreadingAttribute',  # /CLRTHREADATTRIBUTE:NONE
                            'MTAThreadingAttribute',  # /CLRTHREADATTRIBUTE:MTA
                            'STAThreadingAttribute']))  # /CLRTHREADATTRIBUTE:STA
        _Same(_link, 'Driver',
              _Enumeration(['NotSet',
                            'Driver',  # /Driver
                            'UpOnly',  # /DRIVER:UPONLY
                            'WDM']))  # /DRIVER:WDM
        _Same(_link, 'LinkTimeCodeGeneration',
              _Enumeration(['Default',
                            'UseLinkTimeCodeGeneration',  # /LTCG
                            'PGInstrument',  # /LTCG:PGInstrument
                            'PGOptimization',  # /LTCG:PGOptimize
                            'PGUpdate']))  # /LTCG:PGUpdate
        _Same(_link, 'ShowProgress',
              _Enumeration(['NotSet',
                            'LinkVerbose',  # /VERBOSE
                            'LinkVerboseLib'],  # /VERBOSE:Lib
                           new=['LinkVerboseICF',  # /VERBOSE:ICF
                                'LinkVerboseREF',  # /VERBOSE:REF
                                'LinkVerboseSAFESEH',  # /VERBOSE:SAFESEH
                                'LinkVerboseCLR']))  # /VERBOSE:CLR
        _Same(_link, 'UACExecutionLevel',
              _Enumeration(['AsInvoker',  # /level='asInvoker'
                            'HighestAvailable',  # /level='highestAvailable'
                            'RequireAdministrator']))  # /level='requireAdministrator'
        _Same(_link, 'MinimumRequiredVersion', _string)
        _Same(_link, 'TreatLinkerWarningAsErrors', _boolean)  # /WX


        # Options found in MSVS that have been renamed in MSBuild.
        _Renamed(_link, 'IgnoreDefaultLibraryNames', 'IgnoreSpecificDefaultLibraries',
                 _file_list)  # /NODEFAULTLIB
        _Renamed(_link, 'ResourceOnlyDLL', 'NoEntryPoint', _boolean)  # /NOENTRY
        _Renamed(_link, 'SwapRunFromNet', 'SwapRunFromNET', _boolean)  # /SWAPRUN:NET

        _Moved(_link, 'GenerateManifest', '', _boolean)
        _Moved(_link, 'IgnoreImportLibrary', '', _boolean)
        _Moved(_link, 'LinkIncremental', '', _newly_boolean)
        _Moved(_link, 'LinkLibraryDependencies', 'ProjectReference', _boolean)
        _Moved(_link, 'UseLibraryDependencyInputs', 'ProjectReference', _boolean)

        # MSVS options not found in MSBuild.
        _MSVSOnly(_link, 'OptimizeForWindows98', _newly_boolean)
        _MSVSOnly(_link, 'UseUnicodeResponseFiles', _boolean)

        # MSBuild options not found in MSVS.
        _MSBuildOnly(_link, 'BuildingInIDE', _boolean)
        _MSBuildOnly(_link, 'ImageHasSafeExceptionHandlers', _boolean)  # /SAFESEH
        _MSBuildOnly(_link, 'LinkDLL', _boolean)  # /DLL Visible='false'
        _MSBuildOnly(_link, 'LinkStatus', _boolean)  # /LTCG:STATUS
        _MSBuildOnly(_link, 'PreventDllBinding', _boolean)  # /ALLOWBIND
        _MSBuildOnly(_link, 'SupportNobindOfDelayLoadedDLL', _boolean)  # /DELAY:NOBIND
        _MSBuildOnly(_link, 'TrackerLogDirectory', _folder_name)
        _MSBuildOnly(_link, 'MSDOSStubFileName', _file_name)  # /STUB Visible='false'
        _MSBuildOnly(_link, 'SectionAlignment', _integer)  # /ALIGN
        _MSBuildOnly(_link, 'SpecifySectionAttributes', _string)  # /SECTION
        _MSBuildOnly(_link, 'ForceFileOutput',
                     _Enumeration([], new=['Enabled',  # /FORCE
                                           # /FORCE:MULTIPLE
                                           'MultiplyDefinedSymbolOnly',
                                           'UndefinedSymbolOnly']))  # /FORCE:UNRESOLVED
        _MSBuildOnly(_link, 'CreateHotPatchableImage',
                     _Enumeration([], new=['Enabled',  # /FUNCTIONPADMIN
                                           'X86Image',  # /FUNCTIONPADMIN:5
                                           'X64Image',  # /FUNCTIONPADMIN:6
                                           'ItaniumImage']))  # /FUNCTIONPADMIN:16
        _MSBuildOnly(_link, 'CLRSupportLastError',
                     _Enumeration([], new=['Enabled',  # /CLRSupportLastError
                                           'Disabled',  # /CLRSupportLastError:NO
                                           # /CLRSupportLastError:SYSTEMDLL
                                           'SystemDlls']))

        '''
        SwitchConverter.__init__(self, table, booltable)

CLSWITCHES = ClSwitchConverter()
LINKSWITCHES = LinkSwitchConverter()

#-------------------------------------------------------------------------------

class BuildConfig(object):
    def __init__(self, variant, platform, target, env):
        self.name = '%s|%s' % (variant, platform)
        self.variant = variant
        self.platform = platform
        self.target = target
        self.env = env

def _generateGUID(slnfile, name):
    """This generates a dummy GUID for the sln file to use.  It is
    based on the MD5 signatures of the sln filename plus the name of
    the project.  It basically just needs to be unique, and not
    change with each invocation."""
    m = hashlib.md5()
    # Normalize the slnfile path to a Windows path (\ separators) so
    # the generated file has a consistent GUID even if we generate
    # it on a non-Windows platform.
    m.update(ntpath.normpath(str(slnfile)) + str(name))
    solution = m.hexdigest().upper()
    # convert most of the signature to GUID form (discard the rest)
    solution = "{" + solution[:8] + "-" + solution[8:12] + "-" + solution[12:16] + "-" + solution[16:20] + "-" + solution[20:32] + "}"
    return solution

def _unique_id(seed):
    r = random.Random()
    r.seed (seed)
    s = "{%0.8x-%0.4x-%0.4x-%0.4x-%0.12x}" % (
        r.getrandbits(4*8),
        r.getrandbits(2*8),
        r.getrandbits(2*8),
        r.getrandbits(2*8),
        r.getrandbits(6*8))
    return s

# Return a Windows path from a native path
def winpath(path):
    return ntpath.join(*os.path.split(path))

def xtend(*args):
    result = []
    for a in args:
        if isinstance(a, (list, tuple)):
            result.extend(a)
        else:
            result.append(a)
    return result

def makeList(x):
    if not x:
        return []
    if type(x) is not list:
        return [x]
    return x

#-------------------------------------------------------------------------------

class _ProjectGenerator(object):
    """Generates a project file for MSVS 2013"""

    def __init__(self, project_node, filters_node, source, env):
        self.project_dir = os.path.dirname(os.path.abspath(str(project_node)))
        self.project_node = project_node
        self.project_file = None
        self.filters_node = filters_node
        self.filters_file = None
        self.source = sorted(source)
        self.configs = sorted(env['VSPROJECT_CONFIGS'], key=lambda x: x.name)
        self.excluded_source = env.get('VSPROJECT_EXCLUDED_SOURCE', [])
        self.root_dirs = [os.path.abspath(x) for x in makeList(env['VSPROJECT_ROOT_DIRS'])]

        root_dir = os.getcwd()
        self.cpppath = []
        for path in [os.path.abspath(x) for x in makeList(env['CPPPATH'])]:
            common = os.path.commonprefix([path, root_dir])
            if len(common) == len(root_dir):
                self.cpppath.append(winpath(os.path.relpath(path, self.project_dir)))
            else:
                self.cpppath.append(path)

    def writeHeader(self):
        global clSwitches

        encoding = 'utf-8'
        project_guid = _generateGUID(str(self.project_node), 'x')
        name = 'RippleD'

        f = self.project_file
        f.write(V12DSPHeader % locals())
        f.write('\t<ItemGroup Label="ProjectConfigurations">\n')
        for config in self.configs:
            variant = config.variant
            platform = config.platform            
            f.write(V12DSPProjectConfiguration % locals())
        f.write('\t</ItemGroup>\n')
        f.write(V12DSPGlobals % locals())

        f.write('\t<Import Project="$(VCTargetsPath)\Microsoft.Cpp.Default.props" />\n')
        for config in self.configs:
            variant = config.variant
            platform = config.platform
            use_debug_libs = variant == 'Debug'
            f.write(V12DSPPropertyGroup % locals())
        f.write('\t<Import Project="$(VCTargetsPath)\Microsoft.Cpp.props" />\n')
        f.write('\t<ImportGroup Label="ExtensionSettings" />\n')
        if False:
            for config in self.configs:
                variant = config.variant
                platform = config.platform
                f.write(V12DSPImportGroup % locals())
        f.write('\t<PropertyGroup Label="UserMacros" />\n')
        for config in self.configs:
            variant = config.variant
            platform = config.platform
            f.write(V12DSPItemDefinitionGroup % locals())
            # Cl options
            f.write(
                '\t\t<ClCompile>\n'
                '\t\t\t<PrecompiledHeader />\n'
                '\t\t\t<PreprocessorDefinitions>%s%%(PreprocessorDefinitions)</PreprocessorDefinitions>\n'
                '\t\t\t<AdditionalIncludeDirectories>%s%%(AdditionalIncludeDirectories)</AdditionalIncludeDirectories>\n' % (
                    itemList(config.env['CPPDEFINES'], ';'),
                    itemList(self.cpppath, ';')))
            xml = CLSWITCHES.getXml(config.env['CCFLAGS'])
            for opt in xml:
                f.write ('\t\t\t%s\n' % opt)
            f.write('\t\t</ClCompile>\n')
            # Link options
            f.write(
                '\t\t<Link>\n'
                '\t\t\t<AdditionalDependencies>%s%%(AdditionalDependencies)</AdditionalDependencies>\n'
                '\t\t\t<AdditionalLibraryDirectories>%s%%(AdditionalLibraryDirectories)</AdditionalLibraryDirectories>\n' % (
                    itemList(config.env['LIBS'], ';'),
                    itemList(config.env['LIBPATH'], ';')))
            xml = LINKSWITCHES.getXml(config.env['LINKFLAGS'])
            for opt in xml:
                f.write('\t\t\t%s\n' % opt)
            f.write('\t\t</Link>\n')

            f.write('\t</ItemDefinitionGroup>\n')

        self.filters_file.write(_xml_filters_header)

    def getGroup(self, abspath):
        abspath = os.path.dirname(abspath)
        for d in self.root_dirs:
            common = os.path.commonprefix([abspath, d])
            if common == d:
                return winpath(os.path.relpath(abspath, common))
        return os.path.split(abspath)[1]

    def writeGroups(self):
        f = self.filters_file
        groups = set()
        for source in self.source + self.excluded_source:
            group = self.getGroup(os.path.abspath(str(source)))
            while group != '':
                groups.add(group)
                group = ntpath.split(group)[0]
        for group in sorted(groups):
            guid = _unique_id(group)
            f.write(
                '\t\t<Filter Include="%(group)s">\n'
                '\t\t\t<UniqueIdentifier>%(guid)s</UniqueIdentifier>\n'
                '\t\t</Filter>\n' % locals())
        f.write('\t</ItemGroup>\n')

    def writeProject(self):
        def whichTag(path):
            ext = os.path.splitext(path)[1]
            if ext in ['.c']:
                return 'ClCompile', 'c'
            elif ext in ['.cc', '.cpp']:
                return 'ClCompile', 'cpp'
            elif ext in ['.h', '.hpp', '.hxx', '.inl', '.inc']:
                return 'ClInclude', 'h'
            return 'None', None

        self.writeGroups()

        f = self.project_file
        self.project_file.write('\t<ItemGroup>\n')
        for source in self.source:
            path = winpath(os.path.relpath(str(source), self.project_dir))
            tag, _ = whichTag(path)
            f.write(
                '\t\t<%(tag)s Include="%(path)s">\n'
                '\t\t</%(tag)s>\n' % locals())
        for source in self.excluded_source:
            path = winpath(os.path.relpath(str(source), self.project_dir))
            tag, _ = whichTag(path)
            if tag == 'ClCompile':
                exclude = '\t\t\t<ExcludedFromBuild>True</ExcludedFromBuild>\n'
            else:
                exclude = ''
            f.write(
                '\t\t<%(tag)s Include="%(path)s">\n'
                '%(exclude)s'
                '\t\t</%(tag)s>\n' % locals())
        f.write('\t</ItemGroup>\n')

        f = self.filters_file
        f.write('\t<ItemGroup>\n')
        for source in self.source + self.excluded_source:
            path = os.path.abspath(str(source))
            group = self.getGroup(path)
            path = winpath(os.path.relpath(path, self.project_dir))
            tag, _ = whichTag(path)
            f.write (
                '\t\t<%(tag)s Include="%(path)s">\n'
                '\t\t\t<Filter>%(group)s</Filter>\n'
                '\t\t</%(tag)s>\n' % locals())
        pass

    def writeFooter(self):
        f = self.project_file
        f.write(
            '\t<Import Project="$(VCTargetsPath)\Microsoft.Cpp.targets" />\n'
            '\t<ImportGroup Label="ExtensionTargets">\n'
            '\t</ImportGroup>\n'
            '</Project>\n')

        self.filters_file.write('\t</ItemGroup>\n</Project>\n')

    def build(self):
        try:
            self.project_file = open(str(self.project_node), 'wb')
        except IOError, detail:
            raise SCons.Errors.InternalError('Unable to open "' +
                str(self.project_node) + '" for writing:' + str(detail))
        try:
            self.filters_file = open(str(self.filters_node), 'wb')
        except IOError, detail:
            raise SCons.Errors.InternalError('Unable to open "' +
                str(self.filters_node) + '" for writing:' + str(detail))
        self.writeHeader()
        self.writeProject()
        self.writeFooter()
        self.project_file.close()
        self.filters_file.close()

#-------------------------------------------------------------------------------

class _SolutionGenerator(object):
    def __init__(self, slnfile, projfile, env):
        pass

    def build(self):
        pass

#-------------------------------------------------------------------------------

# Generate the VS2013 project
def buildProject(target, source, env):
    if env.get('auto_build_solution', 1):
        if len(target) != 3:
            raise ValueError ("Unexpected len(target) != 3")
    if not env.get('auto_build_solution', 1):
        if len(target) != 2:
            raise ValueError ("Unexpected len(target) != 2")

    g = _ProjectGenerator (target[0], target[1], source, env)
    g.build()

    #sources, headers = FindAllSourceFiles(env['VSPROJECT_TARGETS'])
    #g = _ProjectGenerator (target[0], target[1], sources + headers, env)

    if env.get('auto_build_solution', 1):
        g = _SolutionGenerator (target[2], target[0], env)
        g.build()

def projectEmitter(target, source, env):
    if len(target) != 1:
        raise ValueError ("Exactly one target must be specified")

    # If source is unspecified this condition will be true
    if source[0] == target[0]:
        source = []

    outputs = []
    for node in list(target):
        path = env.GetBuildPath(node)
        outputs.extend([
            path + '.vcxproj',
            path + '.vcxproj.filters'])
        if env.get('auto_build_solution', 1):
            outputs.append(path + '.sln')
    return outputs, source

projectBuilder = SCons.Builder.Builder(
    action = buildProject,
    emitter = projectEmitter)

def createConfig(self, variant, platform, target, env):
    return BuildConfig(variant, platform, target, env)

def generate(env):
    """Add Builders and construction variables for Microsoft Visual
    Studio project files to an Environment."""
    try:
      env['BUILDERS']['VSProject']
    except KeyError:
      env['BUILDERS']['VSProject'] = projectBuilder
    env.AddMethod(createConfig, 'VSProjectConfig')

def exists(env):
    return True
