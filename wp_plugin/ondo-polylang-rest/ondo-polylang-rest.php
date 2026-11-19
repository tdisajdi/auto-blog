<?php
/**
 * Plugin Name: ondo Polylang REST
 * Description: Polylang(무료판)의 글 언어 지정·번역 연결을 REST API로 여는 작은 전용 플러그인. ondo 자동 발행용.
 * Version: 1.0.1
 * Author: ondo
 * License: GPL-2.0-or-later
 * Requires PHP: 7.4
 *
 * 하는 일(이 셋뿐):
 *   GET  /ondo/v1/languages            - 사이트 언어 목록
 *   GET  /ondo/v1/lang/<id>            - 글(페이지)의 언어와 번역 연결 읽기
 *   POST /ondo/v1/lang/<id>  {lang}    - 글 언어 지정
 *   POST /ondo/v1/link {translations:{ko:1,en:2}} - 번역 연결 후 실제로 연결됐는지 다시 읽어 돌려줌
 *   GET  /ondo/v1/unassigned/<post|page> - 언어가 안 정해진 글 목록
 * 권한: 해당 글을 고칠 수 있는 로그인 사용자만.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

function ondo_pll_ready() {
	return function_exists( 'pll_set_post_language' ) && function_exists( 'pll_save_post_translations' )
		&& function_exists( 'pll_get_post_language' ) && function_exists( 'pll_get_post_translations' )
		&& function_exists( 'pll_languages_list' );
}

function ondo_pll_missing() {
	return new WP_Error( 'ondo_no_polylang', 'Polylang이 켜져 있지 않습니다.', array( 'status' => 503 ) );
}

function ondo_pll_state( $id ) {
	$id = (int) $id;
	return array(
		'id'           => $id,
		'type'         => get_post_type( $id ),
		'status'       => get_post_status( $id ),
		'lang'         => pll_get_post_language( $id, 'slug' ) ?: null,
		'translations' => (object) pll_get_post_translations( $id ),
	);
}

function ondo_pll_can_edit( $request ) {
	$id = (int) $request['id'];
	return $id > 0 && get_post( $id ) && current_user_can( 'edit_post', $id );
}

add_action( 'rest_api_init', function () {
	register_rest_route( 'ondo/v1', '/languages', array(
		'methods'             => 'GET',
		'permission_callback' => function () { return current_user_can( 'edit_posts' ); },
		'callback'            => function () {
			if ( ! ondo_pll_ready() ) { return ondo_pll_missing(); }
			return array( 'languages' => pll_languages_list( array( 'fields' => 'slug' ) ), 'default' => function_exists( 'pll_default_language' ) ? pll_default_language() : null );
		},
	) );

	register_rest_route( 'ondo/v1', '/lang/(?P<id>\d+)', array(
		array(
			'methods'             => 'GET',
			'permission_callback' => 'ondo_pll_can_edit',
			'callback'            => function ( $request ) {
				if ( ! ondo_pll_ready() ) { return ondo_pll_missing(); }
				return ondo_pll_state( $request['id'] );
			},
		),
		array(
			'methods'             => 'POST',
			'permission_callback' => 'ondo_pll_can_edit',
			'args'                => array( 'lang' => array( 'required' => true, 'type' => 'string' ) ),
			'callback'            => function ( $request ) {
				if ( ! ondo_pll_ready() ) { return ondo_pll_missing(); }
				$lang = sanitize_key( $request['lang'] );
				if ( ! in_array( $lang, pll_languages_list( array( 'fields' => 'slug' ) ), true ) ) {
					return new WP_Error( 'ondo_bad_lang', '사이트에 없는 언어입니다: ' . $lang, array( 'status' => 400 ) );
				}
				pll_set_post_language( (int) $request['id'], $lang );
				clean_post_cache( (int) $request['id'] );
				return ondo_pll_state( $request['id'] );
			},
		),
	) );

	register_rest_route( 'ondo/v1', '/link', array(
		'methods'             => 'POST',
		'permission_callback' => function () { return current_user_can( 'edit_posts' ); },
		'args'                => array( 'translations' => array( 'required' => true ) ),
		'callback'            => function ( $request ) {
			if ( ! ondo_pll_ready() ) { return ondo_pll_missing(); }
			$langs = pll_languages_list( array( 'fields' => 'slug' ) );
			$pairs = array();
			foreach ( (array) $request['translations'] as $lang => $id ) {
				$lang = sanitize_key( $lang );
				$id   = (int) $id;
				if ( ! in_array( $lang, $langs, true ) || ! get_post( $id ) || ! current_user_can( 'edit_post', $id ) ) {
					return new WP_Error( 'ondo_bad_pair', '연결할 수 없는 짝: ' . $lang . '=' . $id, array( 'status' => 400 ) );
				}
				if ( pll_get_post_language( $id, 'slug' ) !== $lang ) {
					pll_set_post_language( $id, $lang );   // 연결 전에 각 글 언어를 먼저 맞춤(순서가 틀리면 연결이 조용히 안 됨)
				}
				$pairs[ $lang ] = $id;
			}
			if ( count( $pairs ) < 2 ) {
				return new WP_Error( 'ondo_need_two', '두 언어 이상이 필요합니다.', array( 'status' => 400 ) );
			}
			pll_save_post_translations( $pairs );
			$out = array();
			foreach ( $pairs as $lang => $id ) {
				clean_post_cache( $id );
				$out[] = ondo_pll_state( $id );
			}
			$ok = true;
			foreach ( $out as $st ) {
				foreach ( $pairs as $lang => $id ) {
					$t = (array) $st['translations'];
					if ( ! isset( $t[ $lang ] ) || (int) $t[ $lang ] !== $id ) { $ok = false; }
				}
			}
			return array( 'linked' => $ok, 'posts' => $out );
		},
	) );

	register_rest_route( 'ondo/v1', '/unassigned/(?P<type>post|page)', array(
		'methods'             => 'GET',
		'permission_callback' => function () { return current_user_can( 'edit_posts' ); },
		'callback'            => function ( $request ) {
			if ( ! ondo_pll_ready() ) { return ondo_pll_missing(); }
			$type = in_array( $request['type'], array( 'post', 'page' ), true ) ? $request['type'] : 'page';
			$ids  = get_posts( array( 'post_type' => $type, 'post_status' => array( 'publish', 'draft', 'private', 'pending' ), 'numberposts' => 200, 'fields' => 'ids', 'lang' => '' ) );
			$none = array();
			foreach ( $ids as $id ) {
				if ( ! pll_get_post_language( $id, 'slug' ) ) { $none[] = (int) $id; }
			}
			return array( 'type' => $type, 'checked' => count( $ids ), 'no_language' => $none );
		},
	) );
} );
