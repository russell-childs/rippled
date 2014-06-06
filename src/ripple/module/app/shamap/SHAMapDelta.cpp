//------------------------------------------------------------------------------
/*
    This file is part of rippled: https://github.com/ripple/rippled
    Copyright (c) 2012, 2013 Ripple Labs Inc.

    Permission to use, copy, modify, and/or distribute this software for any
    purpose  with  or without fee is hereby granted, provided that the above
    copyright notice and this permission notice appear in all copies.

    THE  SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
    WITH  REGARD  TO  THIS  SOFTWARE  INCLUDING  ALL  IMPLIED  WARRANTIES  OF
    MERCHANTABILITY  AND  FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
    ANY  SPECIAL ,  DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
    WHATSOEVER  RESULTING  FROM  LOSS  OF USE, DATA OR PROFITS, WHETHER IN AN
    ACTION  OF  CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
    OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
*/
//==============================================================================

namespace ripple {

// This code is used to compare another node's transaction tree
// to our own. It returns a map containing all items that are different
// between two SHA maps. It is optimized not to descend down tree
// branches with the same branch hash. A limit can be passed so
// that we will abort early if a node sends a map to us that
// makes no sense at all. (And our sync algorithm will avoid
// synchronizing matching brances too.)

class SHAMapDeltaNode
{
public:
    SHAMapNode mNodeID;
    uint256 mOurHash, mOtherHash;

    SHAMapDeltaNode (const SHAMapNode& id, uint256 const& ourHash, uint256 const& otherHash) :
        mNodeID (id), mOurHash (ourHash), mOtherHash (otherHash)
    {
        ;
    }
};

//RJCHILDS start of mod
// Function description:
// node and otherMapItiem belong to the same Node ID. isFirstMap is true if node belongs to this_tree, false
// if it belongs to other_tree. diffrerences contains a set of
// std::pair<item_tag, std::pair<this_tree_item_or_null, other_tree_item_or_null> >
// If node is an inner node, this function obtains all the leaf items that can be reached from node, in left to right order.
// For each leaf reachable from node, if the item tag > other_tree item tag, then other_tree item is missing from first map
//			std::pair<item_tag, std::pair<null, other_tree_item> > i.e. it is a deleted item in this_tree if it is node.
//			std::pair<item_tag, std::pair<other_tree_item, null > i.e. it is a new item in this_tree if other_tree is node.
// For each leaf reachable from node, if the item tag == other_tree item tag and data is different, then other_tree item is a modified item
//			std::pair<item_tag, std::pair<this_tree_item, other_tree_item > if this_tree is node
//			std::pair<item_tag, std::pair<other_tree_item, this_tree_item > if other_tree is node
//RJCHILDS end of mod
bool SHAMap::walkBranch (SHAMapTreeNode* node, SHAMapItem::ref otherMapItem, bool isFirstMap,
                         Delta& differences, int& maxCount)
{
    // Walk a branch of a SHAMap that's matched by an empty branch or single item in the other map
    std::stack<SHAMapTreeNode*> nodeStack;
    nodeStack.push (node);

    bool emptyBranch = !otherMapItem;

    while (!nodeStack.empty ())
    {
        SHAMapTreeNode* node = nodeStack.top ();
        nodeStack.pop ();

        if (node->isInner ())
        {
            // This is an inner node, add all non-empty branches
            for (int i = 0; i < 16; ++i)
                if (!node->isEmptyBranch (i))
                    nodeStack.push (getNodePointer (node->getChildNodeID (i), node->getChildHash (i)));
        }
        else
        {
            // This is a leaf node, process its item
            SHAMapItem::pointer item = node->peekItem ();

            if (!emptyBranch && (otherMapItem->getTag () < item->getTag ()))
            {
                // this item comes after the item from the other map, so add the other item
                if (isFirstMap) // this is first map, so other item is from second
                    differences.insert (std::make_pair (otherMapItem->getTag (),
                                                        DeltaRef (SHAMapItem::pointer (), otherMapItem)));
                else
                    differences.insert (std::make_pair (otherMapItem->getTag (),
                                                        DeltaRef (otherMapItem, SHAMapItem::pointer ())));

                if (--maxCount <= 0)
                    return false;

                emptyBranch = true;
            }

            if (emptyBranch || (item->getTag () != otherMapItem->getTag ()))
            {
                // unmatched
                if (isFirstMap)
                    differences.insert (std::make_pair (item->getTag (), DeltaRef (item, SHAMapItem::pointer ())));
                else
                    differences.insert (std::make_pair (item->getTag (), DeltaRef (SHAMapItem::pointer (), item)));

                if (--maxCount <= 0)
                    return false;
            }
            else
            {
                if (item->peekData () != otherMapItem->peekData ())
                {
                    // non-matching items
                    if (isFirstMap)
                        differences.insert (std::make_pair (otherMapItem->getTag (), DeltaRef (item, otherMapItem)));
                    else
                        differences.insert (std::make_pair (otherMapItem->getTag (), DeltaRef (otherMapItem, item)));

                    if (--maxCount <= 0)
                        return false;
                }

                emptyBranch = true;
            }
        }
    }

    if (!emptyBranch)
    {
        // otherMapItem was unmatched, must add
        if (isFirstMap) // this is first map, so other item is from second
            differences.insert (std::make_pair (otherMapItem->getTag (),
                                                DeltaRef (SHAMapItem::pointer (), otherMapItem)));
        else
            differences.insert (std::make_pair (otherMapItem->getTag (),
                                                DeltaRef (otherMapItem, SHAMapItem::pointer ())));

        if (--maxCount <= 0)
            return false;
    }

    return true;
}

bool SHAMap::compare (SHAMap::ref otherMap, Delta& differences, int maxCount)
{
    // compare two hash trees, add up to maxCount differences to the difference table
    // return value: true=complete table of differences given, false=too many differences
    // throws on corrupt tables or missing nodes
    // CAUTION: otherMap is not locked and must be immutable

    assert (isValid () && otherMap && otherMap->isValid ());

    std::stack<SHAMapDeltaNode> nodeStack; // track nodes we've pushed

    ScopedReadLockType sl (mLock);

    if (getHash () == otherMap->getHash ())
        return true;

    nodeStack.push (SHAMapDeltaNode (SHAMapNode (), getHash (), otherMap->getHash ()));

    while (!nodeStack.empty ())
    {
        SHAMapDeltaNode dNode (nodeStack.top ());
        nodeStack.pop ();

        SHAMapTreeNode* ourNode = getNodePointer (dNode.mNodeID, dNode.mOurHash);
        SHAMapTreeNode* otherNode = otherMap->getNodePointer (dNode.mNodeID, dNode.mOtherHash);

        if (!ourNode || !otherNode)
        {
            assert (false);
            throw SHAMapMissingNode (mType, dNode.mNodeID, uint256 ());
        }

        if (ourNode->isLeaf () && otherNode->isLeaf ())
        {
            // two leaves
            if (ourNode->getTag () == otherNode->getTag ())
            {
                if (ourNode->peekData () != otherNode->peekData ())
                {
                    differences.insert (std::make_pair (ourNode->getTag (),
                                                        DeltaRef (ourNode->peekItem (), otherNode->peekItem ())));

                    if (--maxCount <= 0)
                        return false;
                }
            }
            else
            {
                differences.insert (std::make_pair (ourNode->getTag (),
                                                    DeltaRef (ourNode->peekItem (), SHAMapItem::pointer ())));

                if (--maxCount <= 0)
                    return false;

                differences.insert (std::make_pair (otherNode->getTag (),
                                                    DeltaRef (SHAMapItem::pointer (), otherNode->peekItem ())));

                if (--maxCount <= 0)
                    return false;
            }
        }
        else if (ourNode->isInner () && otherNode->isLeaf ())
        {
            if (!walkBranch (ourNode, otherNode->peekItem (), true, differences, maxCount))
                return false;
        }
        else if (ourNode->isLeaf () && otherNode->isInner ())
        {
            if (!otherMap->walkBranch (otherNode, ourNode->peekItem (), false, differences, maxCount))
                return false;
        }
        else if (ourNode->isInner () && otherNode->isInner ())
        {
            for (int i = 0; i < 16; ++i)
                if (ourNode->getChildHash (i) != otherNode->getChildHash (i))
                {
                    if (otherNode->isEmptyBranch (i))
                    {
                        // We have a branch, the other tree does not
                        SHAMapTreeNode* iNode = getNodePointer (ourNode->getChildNodeID (i), ourNode->getChildHash (i));

                        if (!walkBranch (iNode, SHAMapItem::pointer (), true, differences, maxCount))
                            return false;
                    }
                    else if (ourNode->isEmptyBranch (i))
                    {
                        // The other tree has a branch, we do not
                        SHAMapTreeNode* iNode =
                            otherMap->getNodePointer (otherNode->getChildNodeID (i), otherNode->getChildHash (i));

                        if (!otherMap->walkBranch (iNode, SHAMapItem::pointer (), false, differences, maxCount))
                            return false;
                    }
                    else // The two trees have different non-empty branches
                        nodeStack.push (SHAMapDeltaNode (ourNode->getChildNodeID (i),
                                                         ourNode->getChildHash (i), otherNode->getChildHash (i)));
                }
        }
        else
            assert (false);
    }

    return true;
}

//RJCHILDS start of mod
// In: modified_leaves -    leaves that exist in both this_ledeger_tree and parent_ledger_tree but whose data differ
// In: deleted_leaves -     leaves that exist in this_tree but not in parent_tree
// In: new_leaves		-	leaves that exist in parent_tree but not this_tree
//
// Returns: bool - true=no error, false = error
//
// Description: SHAMap::compare returns the set of new, deleted and modified leaves resulting from parent_tree - this_tree.
//				This function "integrates" over incremental differences between trees adding new leaves, deleting
//              deleted leaves and modifying modified leaves. The end result is the transformation
//				this_tree --> this_tree + (parent_tree - this_tree) = parent_tree
//
// Assumptions:
//	(1) After conversion, this_tree will have the same number of leaves as parent_tree.
//  (2) this_tree exceeds parent_tree in height by no more than 1 level.
//  (3) The position of a node in the tree depends solely on its hash value.
//  (4) Two successive ledger trees with the same number of leaves and the same set of leaf items are identical in their
//		root, inner and leaf nodes
//  (5) Given a set of new leaves in parent_tree, calling addGuiveItem for each of these new leaves will add them to this_tree
//  (6) Given a set of deleted leaves in parent_tree, calling delIitem for each of these deleted leaves will remove the
//		corresponding leaves and branches from this_tree.
//  (7) Given a set of modified leaves in parent_tree, calling updateGiveItem for each of the modified leaves will update the
//		corresponding leaves in this_tree.
//  (8) Transcations leaf differences are confined to new and modified, there are no deleted leaf items.

// Overloaded function for state map leaves
bool SHAMap::integrate (
        const std::set<SHAMapItem::pointer>& modified_leaves,
        const std::set<SHAMapItem::pointer>& deleted_leaves,
        const std::set<SHAMapItem::pointer>& new_leaves )
{
    //Assume no error until proven wrong
    bool ret_val = true;

    //Integrate over modified leaves
    for( auto& leaf : modified_leaves )
    {
        if( hasItem(leaf->getTag()) ) //Verify leaf exists
        {
            updateGiveItem(leaf, false, false);
        }
        else //inconsistency between fetch pack and this_tree
        {
            ret_val = false;
            WriteLog (lsWARNING, SHAMap) << "SHAMap::integrate: Inconsistency Alert."
                    << " A compact fetch pack contains a modified account state leaf that does not exist in this tree.";
        }
    }

    //Integrate over deleted leaves
    for( auto& leaf : deleted_leaves )
    {
        if( hasItem(leaf->getTag()) ) //Verify leaf exists
        {
            delItem(leaf->getTag());
        }
        else	//inconsistency between fetch pack and this_tree
        {
            ret_val = false;
            WriteLog (lsWARNING, SHAMap) << "SHAMap::integrate: Inconsistency Alert."
                    << " A compact fetch pack contains a deleted account state leaf that does not exist in this tree.";
        }
    }

    //Integrate over modified leaves
    for( auto& leaf : new_leaves )
    {
        if( !hasItem(leaf->getTag()) ) //Verify leaf does not exist
        {
            addGiveItem(leaf, false, false);
        }
        else //inconsistency between fetch pack and this_tree
        {
            ret_val = false;
            WriteLog (lsWARNING, SHAMap) << "SHAMap::integrate: Inconsistency Alert."
                    << " A compact fetch pack contains a new account state leaf that already exists in this tree.";
        }
    }

    return ret_val;
}

// Overloaded function for transaction leaves
// Assumptions: Transactions have no metadata
bool SHAMap::integrate ( const std::set<SHAMapItem::pointer>& transaction_without_meta_data_leaves/*,
                         const std::set<SHAMapItem::pointer>& transaction_with_meta_data_leaves*/ )
{
    //Assume no error until proven wrong
    bool ret_val = true;

    //Integrate over transaction-without-meta-data leaves
    for( auto& leaf : transaction_without_meta_data_leaves )
    {
        if( hasItem(leaf->getTag()) ) //Leaf exists, so modify it
        {
            updateGiveItem(leaf, true, false);
        }
        else //new leaf, so add it
        {
            addGiveItem(leaf, true, false);
        }
    }

    //Integrate over transaction-with-meta-data leaves
    /*
    for( auto& leaf : transaction_with_meta_data_leaves )
    {
        if( hasItem(leaf->getTag()) ) //Leaf exists, so modify it
        {
            updateGiveItem(leaf, true, true);
        }
        else //new leaf, so add it
        {
            addGiveItem(leaf, true, true);
        }
    }
    */

    return ret_val;
}
//RJCHILDS end of mod

void SHAMap::walkMap (std::vector<SHAMapMissingNode>& missingNodes, int maxMissing)
{
    std::stack<SHAMapTreeNode::pointer> nodeStack;

    ScopedReadLockType sl (mLock);

    if (!root->isInner ())  // root is only node, and we have it
        return;

    nodeStack.push (root);

    while (!nodeStack.empty ())
    {
        SHAMapTreeNode::pointer node = nodeStack.top ();
        nodeStack.pop ();

        for (int i = 0; i < 16; ++i)
            if (!node->isEmptyBranch (i))
            {
                try
                {
                    SHAMapTreeNode::pointer d = getNode (node->getChildNodeID (i), node->getChildHash (i), false);

                    if (d->isInner ())
                        nodeStack.push (d);
                }
                catch (SHAMapMissingNode& n)
                {
                    missingNodes.push_back (n);

                    if (--maxMissing <= 0)
                        return;
                }
            }
    }
}

} // ripple
