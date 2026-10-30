
package com.example.drm.mpd;

import com.example.drm.discord.DiscordUploader.UploadResult;
import com.example.drm.util.Log;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NamedNodeMap;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.OutputKeys;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public class MpdRewriter {

    private static final String MPD_NS =
            "urn:mpeg:dash:schema:mpd:2011";

    private static final String CENC_NS =
            "urn:mpeg:cenc:2013";

    private static final String CP =
            "ContentProtection";

    public void rewrite(
            Path mpd,
            Map<String, UploadResult> uploaded,
            String kid
    ) throws Exception {

        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newInstance();

        factory.setNamespaceAware(true);

        Document document =
                factory.newDocumentBuilder()
                        .parse(mpd.toFile());

        Element root =
                document.getDocumentElement();

        root.setAttribute(
                "xmlns:cenc",
                CENC_NS
        );

        /*
         * Add CENC / ClearKey protection
         * to every AdaptationSet.
         */
        NodeList adaptationSets =
                root.getElementsByTagNameNS(
                        MPD_NS,
                        "AdaptationSet"
                );

        for (int i = 0;
             i < adaptationSets.getLength();
             i++) {

            addProtection(
                    document,
                    (Element) adaptationSets.item(i),
                    kid
            );
        }

        /*
         * Find all SegmentTemplate elements.
         */
        NodeList templates =
                root.getElementsByTagNameNS(
                        MPD_NS,
                        "SegmentTemplate"
                );

        List<Element> templateCopy =
                new ArrayList<>();

        for (int i = 0;
             i < templates.getLength();
             i++) {

            templateCopy.add(
                    (Element) templates.item(i)
            );
        }

        /*
         * Convert each SegmentTemplate
         * into a SegmentList containing
         * absolute CDN resolver URLs.
         */
        for (Element template : templateCopy) {

            Element representation =
                    parentRepresentation(template);

            if (representation == null) {
                continue;
            }

            String representationId =
                    representation.getAttribute("id");

            String initialization =
                    template.getAttribute("initialization");

            if (representationId.isBlank()
                    || initialization.isBlank()) {
                continue;
            }

            String initializationName =
                    initialization.replace(
                            "$RepresentationID$",
                            representationId
                    );

            UploadResult initializationUpload =
                    uploaded.get(
                            Path.of(initializationName)
                                    .getFileName()
                                    .toString()
                    );

            if (initializationUpload == null) {

                throw new IllegalStateException(
                        "Initialization not uploaded: "
                                + initializationName
                );
            }

            /*
             * Create SegmentList.
             */
            Element segmentList =
                    document.createElementNS(
                            MPD_NS,
                            "SegmentList"
                    );

            /*
             * Copy SegmentTemplate attributes
             * except initialization and media.
             */
            NamedNodeMap attributes =
                    template.getAttributes();

            for (int i = 0;
                 i < attributes.getLength();
                 i++) {

                Node attribute =
                        attributes.item(i);

                if (!attribute.getNodeName()
                                .equals("initialization")
                        && !attribute.getNodeName()
                                .equals("media")) {

                    segmentList.setAttribute(
                            attribute.getNodeName(),
                            attribute.getNodeValue()
                    );
                }
            }

            /*
             * Add initialization URL.
             */
            Element initializationElement =
                    document.createElementNS(
                            MPD_NS,
                            "Initialization"
                    );

            initializationElement.setAttribute(
                    "sourceURL",
                    initializationUpload.resolverUrl()
            );

            segmentList.appendChild(
                    initializationElement
            );

            /*
             * Preserve SegmentTimeline.
             */
            Node timeline =
                    firstChild(
                            template,
                            "SegmentTimeline"
                    );

            if (timeline != null) {

                segmentList.appendChild(
                        timeline.cloneNode(true)
                );
            }

            /*
             * Find all uploaded media segments.
             */
            String prefix =
                    "chunk-"
                            + representationId
                            + "-";

            try (var stream =
                         Files.list(mpd.getParent())) {

                stream
                        .filter(
                                path ->
                                        Files.isRegularFile(path)
                                                && path.getFileName()
                                                .toString()
                                                .startsWith(prefix)
                                                && path.getFileName()
                                                .toString()
                                                .endsWith(".m4s")
                        )
                        .sorted()
                        .forEach(path -> {

                            String filename =
                                    path.getFileName()
                                            .toString();

                            UploadResult upload =
                                    uploaded.get(filename);

                            if (upload == null) {

                                throw new RuntimeException(
                                        "Segment not uploaded: "
                                                + filename
                                );
                            }

                            Element segmentUrl =
                                    document.createElementNS(
                                            MPD_NS,
                                            "SegmentURL"
                                    );

                            segmentUrl.setAttribute(
                                    "media",
                                    upload.resolverUrl()
                            );

                            segmentList.appendChild(
                                    segmentUrl
                            );
                        });
            }

            /*
             * Replace SegmentTemplate with
             * the generated SegmentList.
             */
            Node parent =
                    template.getParentNode();

            parent.replaceChild(
                    segmentList,
                    template
            );
        }

        /*
         * Write modified MPD back to disk.
         */
        Transformer transformer =
                TransformerFactory
                        .newInstance()
                        .newTransformer();

        transformer.setOutputProperty(
                OutputKeys.INDENT,
                "yes"
        );

        transformer.setOutputProperty(
                OutputKeys.ENCODING,
                "UTF-8"
        );

        transformer.transform(
                new DOMSource(document),
                new StreamResult(mpd.toFile())
        );

        Log.ok(
                "MPD rewritten with CDN resolver URLs"
        );
    }

    private Element parentRepresentation(
            Element template
    ) {

        Node node =
                template.getParentNode();

        while (node != null) {

            if (node instanceof Element element
                    && "Representation".equals(
                    element.getLocalName()
            )) {

                return element;
            }

            node = node.getParentNode();
        }

        return null;
    }

    private Node firstChild(
            Element element,
            String localName
    ) {

        NodeList nodes =
                element.getElementsByTagNameNS(
                        MPD_NS,
                        localName
                );

        if (nodes.getLength() == 0) {
            return null;
        }

        return nodes.item(0);
    }

    private void addProtection(
            Document document,
            Element adaptationSet,
            String kid
    ) {

        /*
         * Remove existing ContentProtection
         * elements.
         */
        for (Node node = newChildList(adaptationSet);
             node != null; ) {

            Node next =
                    node.getNextSibling();

            if (node instanceof Element element
                    && CP.equals(
                    element.getLocalName()
            )) {

                adaptationSet.removeChild(node);
            }

            node = next;
        }

        String formattedKid =
                formatKid(kid);

        /*
         * MPEG-CENC ContentProtection.
         */
        Element cencProtection =
                document.createElementNS(
                        MPD_NS,
                        CP
                );

        cencProtection.setAttribute(
                "schemeIdUri",
                "urn:mpeg:dash:mp4protection:2011"
        );

        cencProtection.setAttribute(
                "value",
                "cenc"
        );

        cencProtection.setAttributeNS(
                CENC_NS,
                "cenc:default_KID",
                formattedKid
        );

        adaptationSet.insertBefore(
                cencProtection,
                adaptationSet.getFirstChild()
        );

        /*
         * ClearKey ContentProtection.
         */
        Element clearKeyProtection =
                document.createElementNS(
                        MPD_NS,
                        CP
                );

        clearKeyProtection.setAttribute(
                "schemeIdUri",
                "urn:uuid:e2719d58-a985-b3c9-781a-b030af78d30e"
        );

        clearKeyProtection.setAttribute(
                "value",
                "ClearKey1.0"
        );

        adaptationSet.insertBefore(
                clearKeyProtection,
                cencProtection.getNextSibling()
        );
    }

    private Node newChildList(Element element) {
        return element.getFirstChild();
    }

    private String formatKid(String value) {

        value = value
                .replace("-", "")
                .toLowerCase(Locale.ROOT);

        if (!value.matches("[0-9a-f]{32}")) {

            throw new IllegalArgumentException(
                    "Invalid KID"
            );
        }

        return value.substring(0, 8)
                + "-"
                + value.substring(8, 12)
                + "-"
                + value.substring(12, 16)
                + "-"
                + value.substring(16, 20)
                + "-"
                + value.substring(20);
    }
}
