//This file to be compiled when the system is in "system test mode".
//When the system is in production mode, this file shall not be compiled.
//This file aliases protocl::otGetObjectByHash with protocol::otRipple_Labs_Test_Message_GetObjectByHash
//This alias will allow Ripple Labs to run tests using messages that are ignored by user machines on the netowrk
//This alias is declared in the *.proto file in this directory

#define TMGetObjectByHash Ripple_Labs_Test_Message_TMGetObjectByHash
#include "RootDirectory/rippled/src/ripple_overlay/impl/PeerImp.cpp"
#undef TMGetObjectByHash
